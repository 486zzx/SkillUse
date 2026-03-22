"""
周边搜索 HTTP 请求封装层。
必须传入 http_client 发起异步 GET。
对上层暴露 geocode / around_search 业务接口。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from client.http_client import HttpClientBase

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from skill_logging._log import init_logger, log_event

init_logger("surround_search")

from config import (
    AROUND_URL,
    DEFAULT_RADIUS,
    GEOCODE_URL,
    REQUEST_TIMEOUT_SECONDS,
)


async def _http_get(url: str, params: dict, http_client: HttpClientBase) -> dict:
    """异步 GET。"""
    _status, body = await http_client.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    if isinstance(body, dict):
        if list(body.keys()) == ["text"] and body.get("text"):
            try:
                parsed = json.loads(body["text"])
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return body
    return {}


async def geocode(
    key: str, address: str, city: str | None, *, http_client: HttpClientBase
) -> dict:
    """高德地理编码，返回第一条结果的坐标 (lng,lat) 或错误信息。"""
    params: dict[str, Any] = {"key": key, "address": address}
    if city:
        params["city"] = city
    log_event(
        "geocode",
        "api_request",
        input={"method": "GET", "url": GEOCODE_URL, "query": params},
        request_body="",
        output_summary={},
        latency_ms=None,
        success=None,
        error="",
    )
    t0 = time.perf_counter()
    data = await _http_get(GEOCODE_URL, params, http_client)
    elapsed = (time.perf_counter() - t0) * 1000
    api_ok = str(data.get("infocode")) == "10000"
    log_event(
        "geocode",
        "api_response",
        level="INFO" if api_ok else "ERROR",
        input={"method": "GET", "url": GEOCODE_URL, "query": params},
        output_summary={"success": api_ok, "infocode": data.get("infocode"), "info": data.get("info")},
        response_body=data,
        latency_ms=elapsed,
        success=api_ok,
        error="" if api_ok else str(data.get("info") or "unknown error"),
    )

    if str(data.get("infocode")) != "10000":
        return {"ok": False, "info": data.get("info") or "未知错误", "infocode": data.get("infocode")}

    geocodes = data.get("geocodes")
    if not isinstance(geocodes, list) or len(geocodes) == 0:
        return {"ok": False, "info": "未找到目标地址"}
    first = geocodes[0]
    if not isinstance(first, dict):
        return {"ok": False, "info": "无坐标"}
    loc = first.get("location")
    if not loc or not isinstance(loc, str):
        return {"ok": False, "info": "无坐标"}
    return {"ok": True, "location": loc}


async def around_search(
    key: str,
    location: str,
    keywords: str,
    city: str | None,
    radius: int,
    page: int = 1,
    *,
    http_client: HttpClientBase,
) -> dict:
    """高德周边搜索。location 为 "经度,纬度"。"""
    params: dict[str, Any] = {
        "key": key,
        "location": location,
        "radius": min(max(0, radius), 50000) or DEFAULT_RADIUS,
        "keywords": keywords,
        "page": max(1, page),
    }
    if city:
        params["city"] = city
    log_event(
        "around_search",
        "api_request",
        input={"method": "GET", "url": AROUND_URL, "query": params},
        request_body="",
        output_summary={},
        latency_ms=None,
        success=None,
        error="",
    )
    t0 = time.perf_counter()
    data = await _http_get(AROUND_URL, params, http_client)
    elapsed = (time.perf_counter() - t0) * 1000
    api_ok = str(data.get("infocode")) == "10000"
    log_event(
        "around_search",
        "api_response",
        level="INFO" if api_ok else "ERROR",
        input={"method": "GET", "url": AROUND_URL, "query": params},
        output_summary={"success": api_ok, "infocode": data.get("infocode"), "info": data.get("info")},
        response_body=data,
        latency_ms=elapsed,
        success=api_ok,
        error="" if api_ok else str(data.get("info") or "unknown error"),
    )
    return data
