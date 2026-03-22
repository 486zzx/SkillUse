"""
Bocha 网页搜索 Fetcher。使用 http_client 统一异步接口。
仅使用响应中的 webPages 信息。
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

BOCHA_URL = "https://api.bocha.cn/v1/web-search"


class BochaFetcher:
    """Bocha 网页搜索 API。"""

    async def fetch(
        self,
        query: str,
        *,
        max_results: int = 20,
        timeout: float = 10,
        client: Any,
    ) -> tuple[str, list[dict], str]:
        key = _config.get_bocha_api_key()
        if not key:
            return "bocha", [], "未配置 BOCHA_API_KEY"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "query": (query or "").strip(),
            "freshness": "noLimit",
            "summary": True,
            "count": min(max_results, 50),  # API 最多返回 50 条结果
        }
        try:
            status, data = await client.post(
                BOCHA_URL,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                timeout=timeout,
            )
            data = data if isinstance(data, dict) else {}
            if int(status) != 200:
                return "bocha", [], data.get("msg") or data.get("text", "") or f"HTTP {status}"
            if data.get("code") != 200:
                return "bocha", [], data.get("msg") or "API 返回错误"
            web_pages = (data.get("data") or {}).get("webPages") or {}
            raw_list = web_pages.get("value") or []
            items = []
            for x in raw_list:
                if not isinstance(x, dict):
                    continue
                title = (x.get("name") or "").strip()
                url = (x.get("url") or "").strip()
                content = (x.get("summary") or x.get("snippet") or "").strip()
                if not url and not title and not content:
                    continue
                items.append({
                    "title": title,
                    "url": url,
                    "content": content,
                    "source": "bocha",
                    "score": None,
                    "date": (x.get("datePublished") or "").strip(),
                })
            return "bocha", items, ""
        except Exception as e:
            return "bocha", [], str(e)


registry.register("bocha", BochaFetcher())
