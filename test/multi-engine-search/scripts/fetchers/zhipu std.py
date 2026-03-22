"""
智谱 Web Search API Fetcher。
API: POST /paas/v4/web_search，返回统一格式 (source_id, items, error)。
"""

from __future__ import annotations

import os
from typing import Any

try:
    import requests
except ImportError:
    requests = None

from .base import registry, Fetcher

ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/web_search"
MAX_QUERY_LEN = 70  # API 建议 search query 不超过 70 字符


class ZhipuStdFetcher:
    """智谱网络搜索 API（search_engine 默认 search_pro_sogou"""

    def fetch(
        self,
        query: str,
        *,
        max_results: int = 5,
        timeout: float = 10,
    ) -> tuple[str, list[dict], str]:
        key = os.environ.get("ZHIPU_API_KEY", "0944e4fd59d14bf79e0aeffadcdb9fc5.vsRaHfsUjme7S9bw").strip()
        if not key:
            return "zhipu-std", [], "未配置 ZHIPU_API_KEY"
        if not requests:
            return "zhipu-std", [], "缺少 requests 库，无法调用智谱 API"
        q = (query or "").strip()
        if len(q) > MAX_QUERY_LEN:
            q = q[:MAX_QUERY_LEN]
        body: dict[str, Any] = {
            "search_query": q,
            "search_engine": "search_std",
            "search_intent": False,
            "count": max_results,
            "search_recency_filter": "noLimit",
            "content_size": "medium",
        }
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        try:
            r = requests.post(ZHIPU_URL, json=body, headers=headers, timeout=timeout)
            data = r.json() if r.content else {}
            if r.status_code != 200:
                err = data.get("error")
                if isinstance(err, dict):
                    msg = err.get("message", str(err))
                else:
                    msg = data.get("message", r.text) or f"HTTP {r.status_code}"
                return "zhipu-std", [], str(msg)[:500]
            raw_list = data.get("search_result") or []
            items = []
            for x in raw_list:
                items.append({
                    "title": (x.get("title") or "").strip(),
                    "url": (x.get("link") or "").strip(),
                    "content": (x.get("content") or "").strip(),
                    "source": "zhipu-std",
                    "score": None,
                    "date": (x.get("publish_date") or "").strip(),
                })
            return "zhipu-std", items, ""
        except Exception as e:
            return "zhipu-std", [], str(e)[:500]


registry.register("zhipu-std", ZhipuStdFetcher())
