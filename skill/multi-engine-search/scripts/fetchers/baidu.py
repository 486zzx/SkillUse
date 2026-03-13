"""
百度千帆搜索 Fetcher。
"""

from __future__ import annotations

from typing import Any

try:
    import requests
except ImportError:
    requests = None

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

    def fetch(
        self,
        query: str,
        *,
        max_results: int = 20,
        timeout: float = 10,
    ) -> tuple[str, list[dict], str]:
        key = _config.get_baidu_api_key()
        if not key:
            return "baidu", [], "未配置 BAIDU_APPBUILDER_API_KEY"
        if not requests:
            return "baidu", [], "缺少 requests 库，无法调用百度 API"
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
            r = requests.post(BAIDU_URL, headers=headers, json=body, timeout=timeout)
            data = r.json()
            if r.status_code != 200 or data.get("code"):
                return "baidu", [], data.get("message", r.text) or f"HTTP {r.status_code}"
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
