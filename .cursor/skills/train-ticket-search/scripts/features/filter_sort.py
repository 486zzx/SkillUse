#!/usr/bin/env python3
"""
车次列表的车型筛选与排序。
车型（固定）：G(高铁/城际), D(动车), Z(直达特快), T(特快), K(快速), O(其他), F(复兴号), S(智能动车组)。
排序：价格/出发时间/到达时间/历时。
"""
from __future__ import annotations

import re
from typing import Any

from features.query_api import get_duration_minutes

from config import (
    TRAIN_TYPE_PREFIX,
    SORT_OPTIONS,
    TIME_RANGE_MINUTES,
    TIME_RANGE_OPTIONS,
)


def _train_type_prefix(train_no: str) -> str:
    """车次号首字母，用于车型筛选。仅识别 TRAIN_TYPE_PREFIX，其余归为 O(其他)。"""
    if not train_no or not isinstance(train_no, str):
        return ""
    t = train_no.strip().upper()
    if t and t[0] in TRAIN_TYPE_PREFIX:
        return t[0]
    return "O"  # 其他归为 O


def _min_price(train: dict[str, Any]) -> float:
    """从 seat_types 中取最低票价，无则 0。"""
    seats = train.get("seat_types") or []
    prices = []
    for s in seats:
        if isinstance(s, dict) and "price" in s:
            try:
                prices.append(float(s["price"]))
            except (TypeError, ValueError):
                pass
    return min(prices) if prices else 0.0


def _time_to_minutes(t: str) -> int:
    """HH:MM 或 HH:mm 转为当日分钟数。"""
    if not t or not isinstance(t, str):
        return 0
    m = re.match(r"(\d{1,2}):(\d{2})", t.strip())
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return 0


def time_range_to_api_name(time_min: str | None, time_max: str | None) -> str | None:
    """
    仅当 (time_min, time_max) 落在某一时段内时返回 凌晨/上午/下午/晚上；
    全天(00:00~23:59) 返回 None，避免误传 departure_time_range 导致只查凌晨班次。
    """
    if not time_min or not time_max:
        return None
    try:
        def to_minutes(hhmm: str) -> int:
            parts = (hhmm or "").strip().split(":")
            return int(parts[0]) * 60 + (int(parts[1]) if len(parts) > 1 else 0)
        lo, hi = to_minutes(time_min), to_minutes(time_max)
        if lo == 0 and hi >= 23 * 60 + 59:
            return None
        for name, (s, e) in TIME_RANGE_MINUTES.items():
            if s <= lo and hi < e:
                return name
    except (ValueError, IndexError):
        pass
    return None


def _in_time_range(minutes: int, range_name: str | None, time_min: int | None, time_max: int | None) -> bool:
    """判断分钟数是否在指定时段或 min/max 范围内。range_name 优先；否则用 time_min/time_max（均为当日分钟，None 表示不限制）。"""
    if range_name and range_name in TIME_RANGE_MINUTES:
        lo, hi = TIME_RANGE_MINUTES[range_name]
        if not (lo <= minutes < hi):
            return False
    if time_min is not None and minutes < time_min:
        return False
    if time_max is not None and minutes > time_max:
        return False
    return True


def filter_by_departure_time(
    trains: list[dict[str, Any]],
    range_name: str | None = None,
    time_min: str | None = None,
    time_max: str | None = None,
) -> list[dict[str, Any]]:
    """
    按出发时刻筛选。range_name: 凌晨/上午/下午/晚上；time_min/time_max: HH:MM，如 08:00 表示不早于 8 点、不晚于 8 点。
    """
    if not range_name and time_min is None and time_max is None:
        return list(trains)
    t_min = _time_to_minutes(time_min) if time_min else None
    t_max = _time_to_minutes(time_max) if time_max else None
    return [
        t for t in trains
        if _in_time_range(_time_to_minutes(t.get("departure_time", "")), range_name, t_min, t_max)
    ]


def filter_by_arrival_time(
    trains: list[dict[str, Any]],
    range_name: str | None = None,
    time_min: str | None = None,
    time_max: str | None = None,
) -> list[dict[str, Any]]:
    """
    按到达时刻筛选。range_name: 凌晨/上午/下午/晚上；time_min/time_max: HH:MM。
    """
    if not range_name and time_min is None and time_max is None:
        return list(trains)
    t_min = _time_to_minutes(time_min) if time_min else None
    t_max = _time_to_minutes(time_max) if time_max else None
    return [
        t for t in trains
        if _in_time_range(_time_to_minutes(t.get("arrival_time", "")), range_name, t_min, t_max)
    ]


def filter_by_train_type(trains: list[dict[str, Any]], train_types: list[str] | None) -> list[dict[str, Any]]:
    """
    按车次号首字母筛选（仅 G/D/Z/T/K 等可从车次号区分）。
    注意：O(其他)/F(复兴号)/S(智能动车组) 无法从车次号可靠区分，主流程应通过 API 的 filter 参数筛选，不调用本函数。
    train_types 为允许的首字母列表，如 ["G","D"]；空或 None 表示不过滤。
    """
    if not train_types:
        return list(trains)
    allow = {t.strip().upper()[0] for t in train_types if t and str(t).strip()}
    if not allow:
        return list(trains)
    return [t for t in trains if _train_type_prefix(t.get("train_no", "")) in allow]


def sort_trains(trains: list[dict[str, Any]], sort_by: str | None) -> list[dict[str, Any]]:
    """
    按 sort_by 排序。支持：price_asc/desc, departure_asc/desc, arrival_asc/desc, duration_asc/desc。
    无效或空 sort_by 则返回原顺序。
    """
    if not sort_by or sort_by not in SORT_OPTIONS:
        return list(trains)
    out = list(trains)

    if sort_by == "price_asc":
        out.sort(key=lambda t: _min_price(t))
    elif sort_by == "price_desc":
        out.sort(key=lambda t: -_min_price(t))
    elif sort_by == "departure_asc":
        out.sort(key=lambda t: _time_to_minutes(t.get("departure_time", "")))
    elif sort_by == "departure_desc":
        out.sort(key=lambda t: -_time_to_minutes(t.get("departure_time", "")))
    elif sort_by == "arrival_asc":
        out.sort(key=lambda t: _time_to_minutes(t.get("arrival_time", "")))
    elif sort_by == "arrival_desc":
        out.sort(key=lambda t: -_time_to_minutes(t.get("arrival_time", "")))
    elif sort_by == "duration_asc":
        out.sort(key=lambda t: get_duration_minutes(t.get("duration", "") or ""))
    elif sort_by == "duration_desc":
        out.sort(key=lambda t: -get_duration_minutes(t.get("duration", "") or ""))

    return out
