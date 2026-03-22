"""
天气查询 HTTP 请求封装层。
由调用方传入 http_client 发起请求，对上层暴露 fetch_daily / fetch_air 业务接口。
"""
from __future__ import annotations

import json
import sys
import traceback
import time
from typing import Any
from pathlib import Path

from client.http_client import HttpClientBase

_SCRIPT_DIR = Path(__file__).resolve().parent.parent

if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from skill_logging._log import init_logger, log_event

init_logger("weather_search")

import config

AIR_PATH = config.AIR_PATH
AIR_SCOPE = config.AIR_SCOPE
BASE_URL = config.BASE_URL
DAILY_PATH = config.DAILY_PATH
REQUEST_TIMEOUT_SECONDS = config.REQUEST_TIMEOUT_SECONDS


async def _seniverse_get(
    path: str, params: dict, auth: dict, *, http_client: HttpClientBase
) -> dict | None:
    """心知 GET 请求，合并 auth 与 params；返回 JSON 或 None。"""
    all_params = {**auth, **params}
    client = http_client
    try:
        url = BASE_URL + path
        log_event(
            "_seniverse_get",
            "api_request",
            input={"method": "GET", "url": url, "query": all_params, "path": path},
            request_body="",
            output_summary={},
            latency_ms=None,
            success=None,
            error="",
        )
        t0 = time.perf_counter()
        status, body = await client.get(url, params=all_params, timeout=REQUEST_TIMEOUT_SECONDS)
        elapsed = (time.perf_counter() - t0) * 1000
        api_ok = 200 <= int(status) < 300
        log_event(
            "_seniverse_get",
            "api_response",
            level="INFO" if api_ok else "ERROR",
            input={"method": "GET", "url": url, "query": all_params, "path": path},
            output_summary={"success": api_ok, "status_code": int(status)},
            response_body=json.dumps(body, ensure_ascii=False),
            latency_ms=elapsed,
            success=api_ok,
            error="" if api_ok else f"http_status={status}",
        )
        if not api_ok:
            log_event(
                "_seniverse_get",
                "http_non_success",
                level="WARNING",
                detail=f"path={path} status={status} body={body.get('text', '')}",
            )
            return None
        if isinstance(body, dict):
            if list(body.keys()) == ["text"] and body.get("text"):
                try:
                    parsed = json.loads(body["text"])
                    return parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    return None
            return body
        return None
    except Exception as e:
        log_event(
            "_seniverse_get",
            "request_exception",
            level="ERROR",
            error=str(e),
            detail=traceback.format_exc(),
        )
        return None


async def fetch_daily(
    location: str,
    auth: dict,
    start: int | str,
    days: int,
    language: str,
    unit: str,
    *,
    http_client: HttpClientBase,
) -> tuple[dict | None, list]:
    """拉取逐日天气；返回 (location_info, daily_list)。"""
    params: dict[str, Any] = {
        "location": location,
        "language": language,
        "unit": unit,
        "start": start,
        "days": days,
    }
    data = await _seniverse_get(DAILY_PATH, params, auth, http_client=http_client)
    if not data:
        return None, []
    results = data.get("results") or []
    if not results:
        return None, []
    r = results[0]
    loc = r.get("location") or {}
    daily = r.get("daily") or []
    return loc, daily


async def fetch_air(
    location: str,
    auth: dict,
    language: str,
    *,
    http_client: HttpClientBase,
) -> dict:
    """拉取空气质量；返回 air 对象或空 dict。"""
    data = await _seniverse_get(
        AIR_PATH,
        {"location": location, "language": language, "scope": AIR_SCOPE},
        auth,
        http_client=http_client,
    )
    if not data:
        return {}
    if isinstance(data.get("status_code"), int) and data.get("status_code") != 200:
        return {}
    results = data.get("results") or []
    if not results:
        return {}
    r = results[0]
    return r.get("air") or r
