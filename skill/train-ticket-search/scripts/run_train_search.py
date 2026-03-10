#!/usr/bin/env python3
"""
列车班次查询总入口。
用法：python run_train_search.py <出发站> <到达站> <出发时间范围> [--arrival-time "到达时间范围"] [--train-type G] [--sort-by price_asc]
出发/到达时间范围格式：yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm（起止用逗号分隔）。配置 PARSE_NATURAL_LANGUAGE_TIME=True 时可接受自然语言。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from config import (
    DEFAULT_MAX_RESULTS,
    PARSE_NATURAL_LANGUAGE_TIME,
)
from filter_sort import (
    filter_by_arrival_time,
    filter_by_departure_time,
    sort_trains,
    SORT_OPTIONS,
    time_range_to_api_name,
)
from query_api import query_trains
from station_resolve import load_stations, resolve_station
from time_utils import (
    parse_arrival_time,
    parse_departure_time,
    parse_standard_arrival_range,
    parse_standard_departure_range,
)


def _ensure_utf8_io() -> None:
    """避免 Windows 控制台 GBK 导致子进程输出解码失败。"""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _output_json(obj: dict, exit_code: int = 0) -> None:
    print(json.dumps(obj, ensure_ascii=False))
    sys.exit(exit_code)


def main() -> None:
    parser = argparse.ArgumentParser(description="列车班次查询")
    parser.add_argument("from_station", help="出发站或出发地（城市/站点名）")
    parser.add_argument("to_station", help="到达站或目的地（城市/站点名）")
    parser.add_argument(
        "departure_time",
        help="出发时间范围，格式：yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm",
    )
    parser.add_argument(
        "--arrival-time",
        default=None,
        metavar="RANGE",
        help="到达时间范围，格式同上",
    )
    parser.add_argument("--train-type", action="append", default=[], metavar="G|D|Z|T|K|O|F|S", help="车型筛选；可多次指定")
    parser.add_argument("--sort-by", choices=list(SORT_OPTIONS), default=None, help="排序方式")
    args = parser.parse_args()

    from_station = (args.from_station or "").strip()
    to_station = (args.to_station or "").strip()
    raw_departure = (args.departure_time or "").strip()

    # ---------- 必填参数校验：不足时走澄清流程 ----------
    missing = []
    if not from_station:
        missing.append("from_station")
    if not to_station:
        missing.append("to_station")
    if not raw_departure:
        missing.append("departure_time")
    if missing:
        err = "缺少必填参数，请补充：出发站、到达站、出发时间（缺一不可）"
        _output_json({
            "success": False,
            "trains": [],
            "total_count": 0,
            "need_clarification": True,
            "missing_params": missing,
            "error": err,
            "message": err,
        }, 1)

    stations = load_stations()
    from_resolved = resolve_station(from_station, stations) if stations else None
    to_resolved = resolve_station(to_station, stations) if stations else None
    if not from_resolved:
        err = f"出发站/出发地「{from_station}」在站点表中无匹配，请检查输入或更换表述。"
        _output_json({
            "success": False,
            "trains": [],
            "total_count": 0,
            "need_clarification": True,
            "missing_params": ["from_station"],
            "error": err,
            "message": err,
        }, 1)
    if not to_resolved:
        err = f"到达站/目的地「{to_station}」在站点表中无匹配，请检查输入或更换表述。"
        _output_json({
            "success": False,
            "trains": [],
            "total_count": 0,
            "need_clarification": True,
            "missing_params": ["to_station"],
            "error": err,
            "message": err,
        }, 1)
    from_station = from_resolved.get("station_name") or from_station
    to_station = to_resolved.get("station_name") or to_station

    # ---------- 时间解析：根据配置决定是否支持自然语言 ----------
    base = datetime.now()
    dep_parsed = None
    if PARSE_NATURAL_LANGUAGE_TIME:
        dep_parsed = parse_standard_departure_range(raw_departure)
        if not dep_parsed:
            dep_parsed = parse_departure_time(raw_departure, base)
    else:
        dep_parsed = parse_standard_departure_range(raw_departure)

    if not dep_parsed or not dep_parsed.get("date"):
        err = (
            "出发时间格式应为 yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm（起止用逗号分隔）"
            if not PARSE_NATURAL_LANGUAGE_TIME
            else f"无法解析出发时间「{raw_departure}」，请检查格式或更换表述。"
        )
        _output_json({
            "success": False,
            "trains": [],
            "total_count": 0,
            "error": err,
            "message": err,
        }, 1)

    departure_date = dep_parsed["date"]
    dep_min = dep_parsed.get("time_min")
    dep_max = dep_parsed.get("time_max")
    api_range = time_range_to_api_name(dep_min, dep_max)

    arr_min, arr_max = None, None
    raw_arrival = (args.arrival_time or "").strip()
    if raw_arrival:
        if PARSE_NATURAL_LANGUAGE_TIME:
            arr_parsed = parse_standard_arrival_range(raw_arrival) or parse_arrival_time(raw_arrival, base)
        else:
            arr_parsed = parse_standard_arrival_range(raw_arrival)
        if arr_parsed:
            arr_min = arr_parsed.get("time_min")
            arr_max = arr_parsed.get("time_max")

    train_filter = ",".join(t.strip().upper()[:1] for t in args.train_type if t) if args.train_type else None
    trains, err = query_trains(
        from_station,
        to_station,
        departure_date,
        train_filter=train_filter,
        departure_time_range=api_range,
    )
    if err:
        _output_json({
            "success": False,
            "trains": [],
            "total_count": 0,
            "error": err,
            "message": err,
        }, 1)

    trains = filter_by_departure_time(
        trains,
        range_name=api_range,
        time_min=dep_min,
        time_max=dep_max,
    )
    trains = filter_by_arrival_time(
        trains,
        range_name=None,
        time_min=arr_min,
        time_max=arr_max,
    )
    trains = sort_trains(trains, args.sort_by)

    if DEFAULT_MAX_RESULTS >= 0:
        trains = trains[:DEFAULT_MAX_RESULTS]

    out = {
        "success": True,
        "trains": trains,
        "total_count": len(trains),
        "query_summary": {
            "from_station": from_station,
            "to_station": to_station,
            "departure_date": departure_date,
            "departure_time": raw_departure,
            "departure_time_min": dep_min,
            "departure_time_max": dep_max,
            "arrival_time": raw_arrival or None,
            "arrival_time_min": arr_min,
            "arrival_time_max": arr_max,
            "train_type": args.train_type or None,
            "sort_by": args.sort_by,
        },
        "error": "",
    }
    if len(trains) == 0:
        out["message"] = "该日期与线路上暂无符合条件的车次，可尝试调整出发日期、放宽筛选条件或更换站点。"
        out["reason"] = out["message"]
    _output_json(out)


if __name__ == "__main__":
    _ensure_utf8_io()
    main()
