#!/usr/bin/env python3
"""
火车票查询：调用聚合数据列车站到站时刻表 API。
接口说明见 docs/train-ticket-search/start.md「API接口信息」。
API 报错时在此记录详细日志，上层对用户统一返回「服务异常，请稍后再试」。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from client.http_client import HttpClientBase

_SCRIPT_DIR = Path(__file__).resolve().parent.parent

if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from skill_logging._log import init_logger, log_event

init_logger("train_search")

from config import (
    TRAIN_API_URL,
    API_KEY,
    API_KEY_ENV,
    DEBUG_ENV,
    API_TIMEOUT_SECONDS,
    API_SEARCH_TYPE,
    API_ENABLE_BOOKING_DEFAULT,
    DEPARTURE_TIME_RANGE_OPTIONS,
)
def _parse_duration_minutes(duration: str) -> int:
    """将历时转为分钟数。支持 04:28、4h28m、4h30m 等格式。"""
    if not duration or not isinstance(duration, str):
        return 0
    s = duration.strip()
    # HH:MM 或 H:MM
    m = re.match(r"(\d{1,2}):(\d{2})", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    total = 0
    for m in re.finditer(r"(\d+)\s*h", s, re.I):
        total += int(m.group(1)) * 60
    for m in re.finditer(r"(\d+)\s*m", s, re.I):
        total += int(m.group(1))
    if "日" in s or "天" in s:
        total += 24 * 60
    return total


async def _call_juhe_train_api(
    departure_station: str,
    arrival_station: str,
    date: str,
    search_type: str = API_SEARCH_TYPE,
    filter_type: str | None = None,
    departure_time_range: str | None = None,
    enable_booking: str = API_ENABLE_BOOKING_DEFAULT,
    *,
    http_client: HttpClientBase,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    调用聚合数据列车站到站时刻表 API。
    请求参数（与 start.md 一致）：
      key              是  string  接口请求 key，个人中心->数据中心->我的API
      search_type      是  string  1-站点名称 2-站点编码
      departure_station 是  string  出发站，如：北京、VNP
      arrival_station  是  string  到达站，如：北京、OHH
      date             是  string  出发日期 yyyy-mm-dd，仅支持今天及之后（不能查昨天及更早），否则接口报错；且仅允许 15 天内
      filter           否  string  车次筛选，如 G 或 G,D。枚举：[G(高铁/城际),D(动车),Z(直达特快),T(特快),K(快速),O(其他),F(复兴号),S(智能动车组)]
      departure_time_range 否  string  出发时段：凌晨/上午/下午/晚上
      enable_booking   否  string  默认 1
    返回 (result 列表, error)。成功时 error 为 None。
    """
    key = (os.environ.get(API_KEY_ENV) or API_KEY or "").strip()
    if not key:
        return [], "请配置环境变量 " + API_KEY_ENV + " 或在 config 中设置 API_KEY（聚合数据接口 key）"

    params = {
        "key": key,
        "search_type": search_type,
        "departure_station": (departure_station or "").strip(),
        "arrival_station": (arrival_station or "").strip(),
        "date": (date or "").strip()[:10],
        "enable_booking": enable_booking,
    }
    if filter_type:
        params["filter"] = filter_type
    if departure_time_range and departure_time_range in DEPARTURE_TIME_RANGE_OPTIONS:
        params["departure_time_range"] = departure_time_range

    try:
        if os.environ.get(DEBUG_ENV):
            import sys
            from urllib.parse import urlencode
            debug_params = {**params, "key": "***" if params.get("key") else ""}
            print(f"JUHE_TRAIN_DEBUG request: {TRAIN_API_URL}?{urlencode(debug_params, encoding='utf-8')}", file=sys.stderr)
        client = http_client
        log_event(
            "_call_juhe_train_api",
            "api_request",
            input={"method": "GET", "url": TRAIN_API_URL, "query": {"search_type": params.get("search_type"), "departure_station": params.get("departure_station"), "arrival_station": params.get("arrival_station"), "date": params.get("date"), "enable_booking": params.get("enable_booking"), "filter": params.get("filter"), "departure_time_range": params.get("departure_time_range")}},
            request_body="",
            output_summary={},
            latency_ms=None,
            success=None,
            error="",
        )
        t0 = time.perf_counter()
        status, body = await client.get(TRAIN_API_URL, params=params, timeout=API_TIMEOUT_SECONDS)
        elapsed = (time.perf_counter() - t0) * 1000
        api_ok = 200 <= int(status) < 300
        log_event(
            "_call_juhe_train_api",
            "api_response",
            level="INFO" if api_ok else "ERROR",
            input={"method": "GET", "url": TRAIN_API_URL, "query": {"search_type": params.get("search_type"), "departure_station": params.get("departure_station"), "arrival_station": params.get("arrival_station"), "date": params.get("date"), "enable_booking": params.get("enable_booking"), "filter": params.get("filter"), "departure_time_range": params.get("departure_time_range")}},
            output_summary={"success": api_ok, "status_code": int(status)},
            response_body=json.dumps(body, ensure_ascii=False),
            latency_ms=elapsed,
            success=api_ok,
            error="" if api_ok else f"http_status={status}",
        )
        if list(body.keys()) == ["text"] and body.get("text"):
            try:
                body = json.loads(body["text"])
            except json.JSONDecodeError:
                body = {}
        if os.environ.get(DEBUG_ENV):
            import sys
            r = body.get("result")
            print(f"JUHE_TRAIN_DEBUG response: error_code={body.get('error_code')} reason={body.get('reason')} result_len={len(r) if isinstance(r, list) else 'not_list'}", file=sys.stderr)
    except (json.JSONDecodeError, OSError, Exception) as e:
        err = f"请求或解析失败: {e}"
        log_event(
            "query_trains",
            "api_parse_error",
            level="WARNING",
            detail=err,
            error=err,
        )
        return [], err

    if body.get("error_code") != 0:
        reason = body.get("reason", "未知错误")
        err = f"接口返回错误: {reason}"
        log_event(
            "query_trains",
            "api_business_error",
            level="WARNING",
            detail=f"{err} (error_code={body.get('error_code')})",
            error=err,
        )
        return [], err

    result = body.get("result")
    if result is None:
        result = []
    if not isinstance(result, list):
        err = "接口返回格式异常"
        log_event("query_trains", "api_format_error", level="WARNING", detail=err, error=err)
        return [], err

    # enable_booking=1 仅可预订时可能因日期未开售而返回空，再试一次返回全部班次
    if len(result) == 0 and enable_booking == "1":
        trains_retry, err_retry = await _call_juhe_train_api(
            departure_station=params["departure_station"],
            arrival_station=params["arrival_station"],
            date=params["date"],
            search_type=search_type,
            filter_type=filter_type,
            departure_time_range=departure_time_range,
            enable_booking=API_ENABLE_BOOKING_DEFAULT,
            http_client=http_client,
        )
        if not err_retry and trains_retry:
            return trains_retry, None

    trains = _map_juhe_result_to_trains(result)
    return trains, None


def _map_juhe_result_to_trains(result: list[Any]) -> list[dict[str, Any]]:
    """
    将聚合 API 的 result 数组映射为统一车次结构。
    API 字段：train_no, departure_station, arrival_station, departure_time, arrival_time, duration(04:28), prices[], train_flags[]。
    """
    trains = []
    for item in result:
        if not isinstance(item, dict):
            continue
        # 历时 API 为 04:28，转为 4h28m 便于排序与展示一致
        dur = (item.get("duration") or "").strip()
        if re.match(r"\d{1,2}:\d{2}", dur):
            parts = dur.split(":", 1)
            dur = f"{int(parts[0])}h{parts[1]}m" if len(parts) == 2 else dur

        prices = item.get("prices") or []
        seat_types = []
        for p in prices:
            if isinstance(p, dict):
                seat_types.append({
                    "name": p.get("seat_name", ""),
                    "price": p.get("price"),
                    "available": p.get("num", ""),
                })

        trains.append({
            "train_no": str(item.get("train_no", "")),
            "from_station": str(item.get("departure_station", "")),
            "to_station": str(item.get("arrival_station", "")),
            "departure_time": str(item.get("departure_time", "")),
            "arrival_time": str(item.get("arrival_time", "")),
            "duration": dur,
            "seat_types": seat_types,
            "train_flags": item.get("train_flags") or [],
        })
    return trains


async def query_trains(
    from_station: str,
    to_station: str,
    departure_date: str,
    train_filter: str | None = None,
    departure_time_range: str | None = None,
    *,
    http_client: HttpClientBase,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    查询火车票班次（聚合数据 API）。
    返回 (trains, error)。成功时 error 为 None；失败时 trains 为空，error 为原因。
    train_filter: 可选，车次筛选如 G、D。
    departure_time_range: 可选，出发时段 凌晨/上午/下午/晚上，传给 API。
    """
    from_station = (from_station or "").strip()
    to_station = (to_station or "").strip()
    departure_date = (departure_date or "").strip()

    if not from_station:
        return [], "出发站不能为空"
    if not to_station:
        return [], "到达站不能为空"
    if not departure_date:
        return [], "出发日期不能为空"

    if len(departure_date) < 10 or departure_date[4:5] != "-" or departure_date[7:8] != "-":
        return [], "出发日期格式应为 yyyy-mm-dd"

    trains, err = await _call_juhe_train_api(
        departure_station=from_station,
        arrival_station=to_station,
        date=departure_date,
        search_type=API_SEARCH_TYPE,
        filter_type=train_filter,
        departure_time_range=departure_time_range,
        http_client=http_client,
    )
    if err:
        return [], err
    return trains, None


def get_duration_minutes(duration: str) -> int:
    """对外暴露：历时字符串 → 分钟。支持 04:28、4h28m。"""
    return _parse_duration_minutes(duration)
