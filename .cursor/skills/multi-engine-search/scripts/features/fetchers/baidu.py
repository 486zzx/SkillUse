"""
百度千帆搜索 Fetcher。使用 http_client 统一异步接口。
"""

from __future__ import annotations

import json
from typing import Any

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

BAIDU_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"


class BaiduFetcher:
    """百度千帆 API。"""

    async def fetch(
        self,
        query: str,
        *,
        max_results: int = 20,
        timeout: float = 10,
        client: Any,
    ) -> tuple[str, list[dict], str]:
        key = _config.get_baidu_api_key()
        if not key:
            return "baidu", [], "未配置 BAIDU_APPBUILDER_API_KEY"
        headers = {
            "X-Appbuilder-Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "messages": [{"content": query.strip(), "role": "user"}],
            "search_source": "baidu_search_v2",
            "edition": "standard",
            "resource_type_filter": [{"type": "web", "top_k": max_results}],
        }
        try:
            status, data = await client.post(
                BAIDU_URL,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                timeout=timeout,
            )
            data = data if isinstance(data, dict) else {}
            if int(status) != 200 or data.get("code"):
                return "baidu", [], data.get("message", data.get("text", "")) or f"HTTP {status}"
            refs = data.get("references") or []
            items = []
            for x in refs:
                items.append({
                    "title": (x.get("title") or "").strip(),
                    "url": (x.get("url") or "").strip(),
                    "content": (x.get("content") or "").strip(),
                    "source": "baidu",
                    "score": x.get("score"),
                    "date": x.get("date") or "",
                })
            return "baidu", items, ""
        except Exception as e:
            return "baidu", [], str(e)


registry.register("baidu", BaiduFetcher())
