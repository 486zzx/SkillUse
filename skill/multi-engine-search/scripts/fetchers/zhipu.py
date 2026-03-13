"""
智谱 Web Search API Fetcher。
API: POST /paas/v4/web_search，返回统一格式 (source_id, items, error)。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

# #region agent log
def _debug_log(msg: str, data: dict, hypothesis_id: str) -> None:
    _log_path = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "debug-8dbb21.log"
    try:
        with open(_log_path, "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"sessionId": "8dbb21", "timestamp": int(time.time() * 1000), "location": "zhipu.py", "message": msg, "data": data, "hypothesisId": hypothesis_id}, ensure_ascii=False) + "\n")
    except Exception:
        pass
# #endregion

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

ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/web_search"
MAX_QUERY_LEN = 70  # API 建议 search query 不超过 70 字符


class ZhipuFetcher:
    """智谱网络搜索 API（search_engine 默认 search_pro_sogou"""

    def fetch(
        self,
        query: str,
        *,
        max_results: int = 20,
        timeout: float = 10,
    ) -> tuple[str, list[dict], str]:
        key = _config.get_zhipu_api_key()
        if not key:
            return "zhipu", [], "未配置 ZHIPU_API_KEY"
        if not requests:
            return "zhipu", [], "缺少 requests 库，无法调用智谱 API"
        q = (query or "").strip()
        if len(q) > MAX_QUERY_LEN:
            q = q[:MAX_QUERY_LEN]
        body: dict[str, Any] = {
            "search_query": q,
            "search_engine": "search_pro_sogou",
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
            # #region agent log
            _debug_log("zhipu_post_done", {"status": r.status_code, "content_len": len(r.content) if r.content else 0}, "H2")
            # #endregion
            data = r.json() if r.content else {}
            if r.status_code != 200:
                err = data.get("error")
                if isinstance(err, dict):
                    msg = err.get("message", str(err))
                else:
                    msg = data.get("message", r.text) or f"HTTP {r.status_code}"
                return "zhipu", [], str(msg)[:500]
            raw_list = data.get("search_result") or []
            items = []
            for x in raw_list:
                items.append({
                    "title": (x.get("title") or "").strip(),
                    "url": (x.get("link") or "").strip(),
                    "content": (x.get("content") or "").strip(),
                    "source": "zhipu",
                    "score": None,
                    "date": (x.get("publish_date") or "").strip(),
                })
            return "zhipu", items, ""
        except Exception as e:
            # #region agent log
            _debug_log("zhipu_except", {"exc_type": type(e).__name__, "exc_msg_prefix": str(e)[:200], "is_unicode_encode": "encode" in str(e).lower() and "unicode" in str(e).lower()}, "H1,H2,H3")
            # #endregion
            return "zhipu", [], str(e)[:500]


registry.register("zhipu", ZhipuFetcher())
