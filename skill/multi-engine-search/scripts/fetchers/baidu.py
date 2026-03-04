"""
百度千帆搜索 Fetcher。
"""

from __future__ import annotations

import os
from typing import Any

try:
    import requests
except ImportError:
    requests = None

from .base import registry, Fetcher

BAIDU_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"
MAX_RESULTS_PER_ENGINE = 5  # 每个引擎每个关键词只取 5 条
# 单次请求超时（秒）；过大会让失败请求拖慢整次聚合墙钟时间
REQUEST_TIMEOUT = 60


class BaiduFetcher:
    """百度千帆 API。"""

    def fetch(self, query: str) -> tuple[str, list[dict], str]:
        key = os.environ.get("BAIDU_APPBUILDER_API_KEY", "your-key").strip()
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
            "resource_type_filter": [{"type": "web", "top_k": min(MAX_RESULTS_PER_ENGINE, 50)}],
        }
        try:
            r = requests.post(BAIDU_URL, headers=headers, json=body, timeout=REQUEST_TIMEOUT)
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
