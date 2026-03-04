#!/usr/bin/env python3
"""
航班查询总入口：一次调用完成 地点→IATA、日期→yyyy-mm-dd、调用 API、可选筛选排序，输出最终结果。
每次执行仅查询一段航班。输入：多个长参数（字符串），无需传 JSON。
  必填（位置参数）：出发地 目的地 日期
  可选（--key 值）：--max-segments 1  --max-price 2000  --sort-by price_asc  --min-departure-time 08:00  --max-departure-time 22:00  --equipment-contains 738
用法：python run_flight_search.py 上海 北京 明天
      python run_flight_search.py 上海 北京 明天 --max-price 2000 --sort-by price_asc
输出：压缩 JSON。成功为 result；失败为 {"success":false,"error":"..."}
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# 可选参数名（命令行 --key 与 options 键对应）
OPTION_KEYS = {
    "max-segments": "maxSegments",
    "max-price": "max_price",
    "sort-by": "sort_by",
    "min-departure-time": "min_departure_time",
    "max-departure-time": "max_departure_time",
    "equipment-contains": "equipment_contains",
}


def _ensure_utf8_io() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _out(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def _parse_args(argv: list[str]) -> tuple[str, str, str, str, dict]:
    """解析 argv：前三个非 flag 为 origin, destination, date；--key value 进入 options 或 max_segments。"""
    args = [a for a in argv if a != ""]
    positionals = []
    options = {}
    max_segments = "1"
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:].strip().lower()
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                val = args[i + 1].strip()
                i += 1
                if key == "max-segments":
                    max_segments = val
                elif key in OPTION_KEYS:
                    opt_key = OPTION_KEYS[key]
                    if opt_key == "max_price":
                        try:
                            options[opt_key] = float(val)
                        except ValueError:
                            options[opt_key] = val
                    else:
                        options[opt_key] = val
            i += 1
            continue
        positionals.append(a)
        i += 1
    origin = (positionals[0] or "").strip() if len(positionals) > 0 else ""
    destination = (positionals[1] or "").strip() if len(positionals) > 1 else ""
    date_raw = (positionals[2] or "").strip() if len(positionals) > 2 else ""
    return origin, destination, date_raw, max_segments, options


def main() -> None:
    _ensure_utf8_io()
    if len(sys.argv) < 4:
        _out({"success": False, "error": "缺少参数：需要 出发地 目的地 日期（三个位置参数），例如：run_flight_search.py 上海 北京 明天"})
        sys.exit(1)

    origin, destination, date_raw, max_segments, options = _parse_args(sys.argv[1:])
    if not origin or not destination or not date_raw:
        _out({"success": False, "error": "缺少出发地、目的地或日期（前三个位置参数必填）"})
        sys.exit(1)

    from location_to_iata import get_data_dir, load_maps, load_airport_map, load_nearest_airport_map, resolve_iata
    from normalize_date import normalize_date
    from query_flight_api import query
    from filter_sort_flights import filter_and_sort

    data_dir = get_data_dir()
    if not (data_dir / "city_map.json").exists():
        _out({"success": False, "error": f"数据目录无效或缺少 city_map.json: {data_dir}"})
        sys.exit(1)

    city_map, province_map = load_maps(data_dir)
    airport_map = load_airport_map(data_dir) or None
    nearest_airport_map = load_nearest_airport_map(data_dir) or None
    base = datetime.now()

    o = resolve_iata(origin, city_map, province_map, airport_map, nearest_airport_map)
    d = resolve_iata(destination, city_map, province_map, airport_map, nearest_airport_map)
    dt = normalize_date(date_raw, time_base=base)

    if not o.get("iata"):
        _out({"success": False, "error": f"无法解析出发地: {origin}"})
        sys.exit(1)
    if not d.get("iata"):
        _out({"success": False, "error": f"无法解析目的地: {destination}"})
        sys.exit(1)
    if not dt.get("date"):
        _out({"success": False, "error": f"无法解析日期: {date_raw}"})
        sys.exit(1)

    dep, arr, date = o["iata"], d["iata"], dt["date"]
    resp = query(departure=dep, arrival=arr, departure_date=date, max_segments=max_segments)

    if resp.get("error_code") != 0:
        _out({
            "success": False,
            "error": resp.get("error") or resp.get("reason") or "API 请求失败",
        })
        sys.exit(1)

    result = resp.get("result", {})
    info = result.get("flightInfo") or []
    if options:
        info = filter_and_sort(info, options)
        result["flightInfo"] = info
        result["flightCount"] = len(info)

    _out({"success": True, "result": result})


if __name__ == "__main__":
    main()
