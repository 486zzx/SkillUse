"""
智谱 Web Search API Fetcher。使用 http_client 统一异步接口。
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


# 非默认模式对应的返回源名（默认 search_pro_sogou 返回 "zhipu"）
ZHIPU_SOURCE_BY_ENGINE = {
    "search_std": "zhipu_std",
    "search_pro": "zhipu_pro",
    "search_pro_quark": "zhipu_quark",
}


class ZhipuFetcher:
    """智谱网络搜索 API（search_engine 默认 search_pro_sogou"""

    def __init__(self, search_engine: str = "search_pro_sogou") -> None:
        # 允许在初始化时注入 search_engine，空值回退到默认值
        self.search_engine = (search_engine or "").strip() or "search_pro_sogou"

    def _source_id(self) -> str:
        """返回本实例对应的源名：默认模式为 zhipu，其他模式为 zhipu_std / zhipu_pro / zhipu_quark。"""
        return ZHIPU_SOURCE_BY_ENGINE.get(self.search_engine, "zhipu")

    async def fetch(
        self,
        query: str,
        *,
        max_results: int = 20,
        timeout: float = 10,
        client: Any,
    ) -> tuple[str, list[dict], str]:
        sid = self._source_id()
        key = _config.get_zhipu_api_key()
        if not key:
            return sid, [], "未配置 ZHIPU_API_KEY"
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
            status, data = await client.post(
                ZHIPU_URL,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                timeout=timeout,
            )
            # #region agent log
            _debug_log(
                "zhipu_post_done",
                {"status": status, "content_len": len((data.get("text") if isinstance(data, dict) else "") or "")},
                "H2",
            )
            # #endregion
            data = data if isinstance(data, dict) else {}
            if int(status) != 200:
                err = data.get("error")
                if isinstance(err, dict):
                    msg = err.get("message", str(err))
                else:
                    msg = data.get("message", data.get("text", "")) or f"HTTP {status}"
                return sid, [], str(msg)[:500]
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
            return sid, items, ""
        except Exception as e:
            # #region agent log
            _debug_log("zhipu_except", {"exc_type": type(e).__name__, "exc_msg_prefix": str(e)[:200], "is_unicode_encode": "encode" in str(e).lower() and "unicode" in str(e).lower()}, "H1,H2,H3")
            # #endregion
            return sid, [], str(e)[:500]


registry.register("zhipu", ZhipuFetcher())
registry.register("zhipu_std", ZhipuFetcher("search_std"))
registry.register("zhipu_pro", ZhipuFetcher("search_pro"))
registry.register("zhipu_quark", ZhipuFetcher("search_pro_quark"))