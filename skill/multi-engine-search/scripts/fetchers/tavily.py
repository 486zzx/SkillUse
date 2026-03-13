"""
Tavily 搜索 Fetcher。
"""

from __future__ import annotations

import json
import urllib.request

from .base import registry, Fetcher

try:
    import config as _config
except ImportError:
    import sys
    from pathlib import Path
    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    import config as _config

TAVILY_MCP_URL = "https://mcp.tavily.com/mcp"


class TavilyFetcher:
    """Tavily MCP 端点。"""

    def fetch(
        self,
        query: str,
        *,
        max_results: int = 20,
        timeout: float = 10,
    ) -> tuple[str, list[dict], str]:
        key = _config.get_tavily_api_key()
        if not key:
            return "tavily", [], "未配置 TAVILY_API_KEY"
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "tavily_search",
                "arguments": {
                    "query": query.strip(),
                    "search_depth": "basic",
                    "topic": "general",
                    "max_results": max_results,
                },
            },
        }
        try:
            req = urllib.request.Request(
                TAVILY_MCP_URL,
                data=json.dumps(body).encode("utf-8"),
                method="POST",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "x-client-source": "multi-engine-search-skill",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
        except Exception as e:
            return "tavily", [], str(e)

        for line in raw.splitlines():
            if not line.startswith("data:"):
                continue
            json_str = line[5:].strip()
            if not json_str:
                continue
            try:
                out = json.loads(json_str)
                if out.get("error"):
                    return "tavily", [], str(out.get("error"))
                # MCP 可能把 API 结果放在 result 里，或直接顶层
                result = out.get("result") or out
                items = self._parse_results(result)
                # 仅当明显是错误信息时才当作 error（避免成功 JSON 里含 "error":null 被误判）
                if len(items) == 1 and not (items[0].get("title") or items[0].get("url")):
                    content = (items[0].get("content") or "").strip()
                    if content and self._looks_like_api_error(content):
                        return "tavily", [], content[:500]
                if items:
                    return "tavily", items, ""
            except json.JSONDecodeError:
                continue
        return "tavily", [], "Tavily 返回无法解析"

    def _looks_like_api_error(self, content: str) -> bool:
        """仅识别明确错误信息，不含 success 型 JSON（如含 "results" 的整包）。"""
        lower = content.lower()
        if "unauthorized" in lower or "401" in content or "invalid api key" in lower or "missing or invalid" in lower:
            return True
        if "error" not in lower:
            return False
        # 成功响应里常有 "error": null，不要误杀；有 "results" 的通常是整包成功 JSON
        if '"results"' in content or "'results'" in lower:
            return False
        return True

    def _parse_results(self, result: dict) -> list[dict]:
        """从 result 中解析出统一 item 列表，兼容多种返回结构。"""
        # 1) result.results / result.structuredContent（数组）
        raw_list = result.get("results") or result.get("structuredContent")
        if isinstance(raw_list, list):
            items = self._items_from_list(raw_list)
            if items:
                return items
        # 2) result.content：可能是 [{"text": "..."}]，text 为整包 JSON 或数组
        content = result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                if "title" in first or "url" in first:
                    return self._items_from_list(content)
                text = (first.get("text") or "").strip()
                if not text:
                    return []
                # 2a) text 为整包 Tavily API JSON：{"query","results",...}
                if text.startswith("{"):
                    try:
                        obj = json.loads(text)
                        if isinstance(obj, dict):
                            raw_list = obj.get("results")
                            if isinstance(raw_list, list):
                                return self._items_from_list(raw_list)
                    except json.JSONDecodeError:
                        pass
                # 2b) text 为数组 JSON
                if text.startswith("["):
                    try:
                        arr = json.loads(text)
                        if isinstance(arr, list):
                            return self._items_from_list(arr)
                    except json.JSONDecodeError:
                        pass
                # 2c) 其他文本当作单条摘要
                return [{"title": "", "url": "", "content": text[:2000], "source": "tavily", "score": None, "date": ""}]
        return []

    def _items_from_list(self, raw_list: list) -> list[dict]:
        items = []
        for x in raw_list:
            if not isinstance(x, dict):
                continue
            title = (x.get("title") or x.get("name") or "").strip()
            url = (x.get("url") or x.get("link") or "").strip()
            content = (x.get("content") or x.get("raw_content") or "").strip()
            if not url and not title and not content:
                continue
            items.append({
                "title": title,
                "url": url,
                "content": content,
                "source": "tavily",
                "score": x.get("score"),
                "date": x.get("date") or "",
            })
        return items


registry.register("tavily", TavilyFetcher())
