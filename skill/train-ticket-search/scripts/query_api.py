#!/usr/bin/env python3
"""
火车票查询：调用聚合数据列车站到站时刻表 API。
接口说明见 docs/train-ticket-search/start.md「API接口信息」。
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# 聚合数据火车票 API（start.md）
TRAIN_API_URL = "https://apis.juhe.cn/fapigw/train/query"
# 环境变量：key 在聚合个人中心 -> 数据中心 -> 我的API 查看
API_KEY_ENV = "JUHE_TRAIN_API_KEY"
DEBUG_ENV = "JUHE_TRAIN_DEBUG"  # 设为 1 时在 stderr 打印请求与原始响应，便于排查空结果


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


# API 出发时段：凌晨 [0:00-06:00)、上午 [6:00-12:00)、下午 [12:00-18:00)、晚上 [18:00-24:00)
DEPARTURE_TIME_RANGE_OPTIONS = ("凌晨", "上午", "下午", "晚上")


def _call_juhe_train_api(
    departure_station: str,
    arrival_station: str,
    date: str,
    search_type: str = "1",
    filter_type: str | None = None,
    departure_time_range: str | None = None,
    enable_booking: str = "2",
) -> tuple[list[dict[str, Any]], str | None]:
    """
    调用聚合数据列车站到站时刻表 API。
    请求参数（与 start.md 一致）：
      key              是  string  接口请求 key，个人中心->数据中心->我的API
      search_type      是  string  1-站点名称 2-站点编码
      departure_station 是  string  出发站，如：北京、VNP
      arrival_station  是  string  到达站，如：北京、OHH
      date             是  string  出发日期 yyyy-mm-dd，仅允许 15 天内
      filter           否  string  车次筛选，如 G 或 G,D。枚举：[G(高铁/城际),D(动车),Z(直达特快),T(特快),K(快速),O(其他),F(复兴号),S(智能动车组)]
      departure_time_range 否  string  出发时段：凌晨/上午/下午/晚上
      enable_booking   否  string  默认 1
    返回 (result 列表, error)。成功时 error 为 None。
    """
    key = (os.environ.get(API_KEY_ENV) or "your-key").strip()
    if not key:
        return [], "请配置环境变量 " + API_KEY_ENV + "（聚合数据接口 key）"

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
        url = TRAIN_API_URL + "?" + urllib.parse.urlencode(params, encoding="utf-8")
        if os.environ.get(DEBUG_ENV):
            import sys
            debug_params = {**params, "key": "***" if params.get("key") else ""}
            print("JUHE_TRAIN_DEBUG request:", TRAIN_API_URL + "?" + urllib.parse.urlencode(debug_params, encoding="utf-8"), file=sys.stderr)
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8")
        body = json.loads(data)
        if os.environ.get(DEBUG_ENV):
            import sys
            r = body.get("result")
            print("JUHE_TRAIN_DEBUG response: error_code=%s reason=%s result_len=%s" % (
                body.get("error_code"), body.get("reason"),
                len(r) if isinstance(r, list) else "not_list"
            ), file=sys.stderr)
    except urllib.error.HTTPError as e:
        return [], f"请求失败: HTTP {e.code}"
    except urllib.error.URLError as e:
        return [], f"请求失败: {e.reason}"
    except (json.JSONDecodeError, OSError) as e:
        return [], f"请求或解析失败: {e}"

    if body.get("error_code") != 0:
        reason = body.get("reason", "未知错误")
        return [], f"接口返回错误: {reason}"

    result = body.get("result")
    if result is None:
        result = []
    if not isinstance(result, list):
        return [], "接口返回格式异常"

    # enable_booking=1 仅可预订时可能因日期未开售而返回空，再试一次返回全部班次
    if len(result) == 0 and enable_booking == "1":
        trains_retry, err_retry = _call_juhe_train_api(
            departure_station=params["departure_station"],
            arrival_station=params["arrival_station"],
            date=params["date"],
            search_type=search_type,
            filter_type=filter_type,
            departure_time_range=departure_time_range,
            enable_booking="2",
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
            "data_source": "juhe",
        })
    return trains


def query_trains(
    from_station: str,
    to_station: str,
    departure_date: str,
    train_filter: str | None = None,
    departure_time_range: str | None = None,
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

    trains, err = _call_juhe_train_api(
        departure_station=from_station,
        arrival_station=to_station,
        date=departure_date,
        search_type="1",
        filter_type=train_filter,
        departure_time_range=departure_time_range,
    )
    if err:
        return [], err
    return trains, None


def get_duration_minutes(duration: str) -> int:
    """对外暴露：历时字符串 → 分钟。支持 04:28、4h28m。"""
    return _parse_duration_minutes(duration)
