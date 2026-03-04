#!/usr/bin/env python3
"""
列车班次查询总入口。
用法：python run_train_search.py <出发站> <到达站> <出发时间> [--arrival-time "五点后"] [--train-type G] [--sort-by price_asc]
出发时间、到达时间均为自然语言时间范围（如「明天」「后天下午五点后」「五点后」），由脚本内用 jionlp 归一为单日日期 + 时间段。
"""
from __future__ import annotations

import argparse
import sys


def _ensure_utf8_io() -> None:
    """避免 Windows 控制台 GBK 导致子进程输出解码失败。"""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import json
from datetime import datetime

from time_utils import parse_departure_time, parse_arrival_time
from query_api import query_trains
from filter_sort import (
    filter_by_departure_time,
    filter_by_arrival_time,
    sort_trains,
    SORT_OPTIONS,
    time_range_to_api_name,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="列车班次查询")
    parser.add_argument("from_station", help="出发站")
    parser.add_argument("to_station", help="到达站")
    parser.add_argument("departure_time", help="出发时间（自然语言），如：明天、后天下午五点后、2025-12-21")
    parser.add_argument("--arrival-time", default=None, metavar="TEXT", help="到达时间范围（自然语言），如：五点后、晚上前")
    parser.add_argument("--train-type", action="append", default=[], metavar="G|D|Z|T|K|O|F|S", help="车型筛选；可多次指定")
    parser.add_argument("--sort-by", choices=list(SORT_OPTIONS), default=None, help="排序方式")
    parser.add_argument("--max-results", type=int, default=None, metavar="N", help="最多返回条数")
    args = parser.parse_args()

    from_station = (args.from_station or "").strip()
    to_station = (args.to_station or "").strip()
    raw_departure = (args.departure_time or "").strip()

    if not from_station:
        out = {"success": False, "trains": [], "total_count": 0, "error": "出发站不能为空"}
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)
    if not to_station:
        out = {"success": False, "trains": [], "total_count": 0, "error": "到达站不能为空"}
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)
    if not raw_departure:
        out = {"success": False, "trains": [], "total_count": 0, "error": "出发时间不能为空"}
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)

    base = datetime.now()
    dep_parsed = parse_departure_time(raw_departure, base)
    if not dep_parsed or not dep_parsed.get("date"):
        out = {
            "success": False,
            "trains": [],
            "total_count": 0,
            "error": f"无法解析出发时间：{raw_departure}，请使用「明天」「后天下午五点后」或 yyyy-mm-dd 等",
        }
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)

    departure_date = dep_parsed["date"]
    dep_min, dep_max = dep_parsed.get("time_min"), dep_parsed.get("time_max")
    api_range = time_range_to_api_name(dep_min, dep_max)

    arr_min, arr_max = None, None
    if args.arrival_time and (args.arrival_time or "").strip():
        arr_parsed = parse_arrival_time((args.arrival_time or "").strip(), base)
        if arr_parsed:
            arr_min, arr_max = arr_parsed.get("time_min"), arr_parsed.get("time_max")

    train_filter = ",".join(t.strip().upper()[:1] for t in args.train_type if t) if args.train_type else None
    trains, err = query_trains(
        from_station,
        to_station,
        departure_date,
        train_filter=train_filter,
        departure_time_range=api_range,
    )
    if err:
        out = {"success": False, "trains": [], "total_count": 0, "error": err}
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)

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

    if args.max_results is not None and args.max_results > 0:
        trains = trains[: args.max_results]

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
            "arrival_time": (args.arrival_time or "").strip() or None,
            "arrival_time_min": arr_min,
            "arrival_time_max": arr_max,
            "train_type": args.train_type or None,
            "sort_by": args.sort_by,
        },
        "error": "",
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    _ensure_utf8_io()
    main()
