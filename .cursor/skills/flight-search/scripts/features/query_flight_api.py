#!/usr/bin/env python3
"""
调用聚合数据航班查询 API。参数通过命令行长参数传入（整段 JSON）。
  python query_flight_api.py '{"departure":"SHA","arrival":"SIA","departureDate":"2025-12-21","maxSegments":"1"}'
输出：完整 API 响应的压缩 JSON；成功时 result 中含 flightInfo 与 flightCount；失败为 {"error":"..."}。

接口限制：仅支持查询今天及之后的航班，不能查询昨天及更早的日期，否则会报「行程出发日期格式不正确或为空」等错误。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import traceback
from datetime import date, datetime
from pathlib import Path

# API 要求的出发日期格式：仅 yyyy-MM-dd
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_SCRIPT_DIR = Path(__file__).resolve().parent.parent

if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from skill_logging._log import init_logger, log_event

init_logger("flight_search")

import config

API_KEY = config.API_KEY
API_KEY_ENV = config.API_KEY_ENV
API_TIMEOUT_SECONDS = config.API_TIMEOUT_SECONDS
API_URL = config.API_URL
DEFAULT_MAX_SEGMENTS = config.DEFAULT_MAX_SEGMENTS

from client.http_client import HttpClientBase


def _ensure_utf8_io() -> None:
    """避免 Windows 控制台 GBK 导致 print 报错或乱码，强制 stdout/stderr 使用 UTF-8。"""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


async def query(
    departure: str,
    arrival: str,
    departure_date: str,  # yyyy-MM-dd，仅支持今天及之后，不能查昨天及更早
    flight_no: str = "",
    max_segments: str | None = None,
    key: str | None = None,
    *,
    http_client: HttpClientBase,
) -> dict:
    max_segments = (max_segments or DEFAULT_MAX_SEGMENTS).strip() or DEFAULT_MAX_SEGMENTS
    key = (key or (API_KEY or os.environ.get(API_KEY_ENV) or "") or "").strip()
    if not key:
        return {"error": "缺少 API Key，请在 config.py 中配置 API_KEY 或设置环境变量 " + API_KEY_ENV, "error_code": -1}

    # API 只接受一个日期，格式 yyyy-MM-dd，不能带时间
    date_only = (departure_date or "").strip()[:10]
    if not date_only or not _DATE_PATTERN.match(date_only):
        return {"error": "行程出发日期格式不正确或为空，请使用 yyyy-MM-dd", "error_code": -1}
    # 仅支持今天及之后的日期，不能查昨天及更早
    try:
        dep_d = datetime.strptime(date_only, "%Y-%m-%d").date()
        if dep_d < date.today():
            return {"error": "出发日期不能早于今天，仅支持查询今天及之后的航班", "error_code": -1}
    except ValueError:
        return {"error": "行程出发日期格式不正确，请使用 yyyy-MM-dd", "error_code": -1}
    # 出发/到达机场代码非空
    dep = (departure or "").strip().upper()
    arr = (arrival or "").strip().upper()
    if not dep or not arr:
        return {"error": "出发地(departure)和目的地(arrival)不能为空", "error_code": -1}
    params = {
        "key": key,
        "departure": dep,
        "arrival": arr,
        "departureDate": date_only,
        "flightNo": (flight_no or "").strip(),
        "maxSegments": max_segments,
    }

    try:
        client = http_client
        log_event(
            "query",
            "api_request",
            input={"method": "GET", "url": API_URL, "query": {"departure": dep, "arrival": arr, "departureDate": date_only, "flightNo": (flight_no or "").strip(), "maxSegments": max_segments}},
            request_body="",
            output_summary={},
            latency_ms=None,
            success=None,
            error="",
        )
        t0 = time.perf_counter()
        status, data = await client.get(API_URL, params=params, timeout=API_TIMEOUT_SECONDS)
        elapsed = (time.perf_counter() - t0) * 1000
        api_ok = 200 <= int(status) < 300
        log_event(
            "query",
            "api_response",
            level="INFO" if api_ok else "ERROR",
            input={"method": "GET", "url": API_URL, "query": {"departure": dep, "arrival": arr, "departureDate": date_only, "flightNo": (flight_no or "").strip(), "maxSegments": max_segments}},
            output_summary={"success": api_ok, "status_code": int(status)},
            response_body=json.dumps(data, ensure_ascii=False),
            latency_ms=elapsed,
            success=api_ok,
            error="" if api_ok else f"http_status={status}",
        )
    except Exception as e:
        log_event(
            "query",
            "api_request_exception",
            level="ERROR",
            error=str(e),
            detail=traceback.format_exc(),
        )
        return {"error": "服务异常，请稍后再试", "error_code": -2}

    if list(data.keys()) == ["text"] and data.get("text"):
        raw = data["text"]
        log_event(
            "query",
            "api_response_not_json",
            level="ERROR",
            detail=f"raw={raw[:500] if raw else ''}",
        )
        return {"error": "服务异常，请稍后再试", "error_code": -3}
    if "_json" in data:
        log_event("query", "api_response_not_object", level="ERROR", detail=str(data))
        return {"error": "服务异常，请稍后再试", "error_code": -3}

    if data.get("error_code") != 0:
        detail = data.get("reason") or data.get("error") or data.get("message") or str(data)
        log_event(
            "query",
            "api_business_error",
            level="ERROR",
            detail=f"error_code={data.get('error_code')}, detail={detail}",
        )
        return {"error": "服务异常，请稍后再试", "error_code": data.get("error_code") or -4}

    # 在结果中附带航班数量，便于展示「共 N 班」
    if isinstance(data.get("result"), dict):
        flight_info = data["result"].get("flightInfo")
        data["result"]["flightCount"] = len(flight_info) if isinstance(flight_info, list) else 0

    return data


def main() -> None:
    _ensure_utf8_io()
    if not sys.argv[1:]:
        print(json.dumps({"error": "缺少输入：请将 JSON 作为命令行参数传入", "error_code": -1}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    raw = " ".join(sys.argv[1:]).strip()
    try:
        if raw.startswith("{"):
            opts = json.loads(raw)
        else:
            opts = {}
    except json.JSONDecodeError:
        opts = {}

    departure = opts.get("departure", "")
    arrival = opts.get("arrival", "")
    departure_date = opts.get("departureDate", "")
    if not departure or not arrival or not departure_date:
        print(
            json.dumps(
                {"error": "缺少必填参数: departure, arrival, departureDate", "error_code": -1},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    from client.http_client import RequestsHttpClient

    result = asyncio.run(
        query(
            departure=departure,
            arrival=arrival,
            departure_date=departure_date,
            flight_no=opts.get("flightNo", ""),
            max_segments=opts.get("maxSegments") or DEFAULT_MAX_SEGMENTS,
            http_client=RequestsHttpClient(),
        )
    )
    # 压缩输出，无缩进与空行，节省 token
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
