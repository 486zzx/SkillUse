#!/usr/bin/env python3
"""
航班查询总入口：一次调用完成 地点→IATA、按出发时间范围查 API、可选筛选排序，输出最终结果。
每次执行仅查询一段航班。入参：出发地、目的地、出发时间范围 [start, end]（标准格式 yyyy-MM-dd HH:mm）；可选到达时间范围、max-price、sort-by。
用法：python run_flight_search.py 上海 北京 --departure-time "2026-03-11 00:00" "2026-03-11 23:59"
      python run_flight_search.py 上海 北京 --departure-time "2026-03-11 00:00" "2026-03-11 23:59" --max-price 2000 --sort-by price_asc
输出：压缩 JSON。成功为 result；失败为 {"success":false,"error":"..."}；参数不足为 {"success":false,"clarification_needed":true,"missing":[...],"message":"..."}
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config import (
    DATETIME_FMT,
    DEFAULT_MAX_SEGMENTS,
    ENABLE_NLP_TIME_RANGE,
    MAX_OUTPUT_FLIGHTS,
)

# 可选参数名（命令行 --key 与 options 键对应），不含时间范围（时间范围单独解析）
OPTION_KEYS = {
    "max-price": "max_price",
    "sort-by": "sort_by",
}

# 标准日期时间格式正则（yyyy-MM-dd HH:mm）
_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}$")


def _ensure_utf8_io() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _out(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def _is_standard_datetime(s: str) -> bool:
    s = (s or "").strip()
    if not s or len(s) < 16:
        return False
    return bool(_DATETIME_PATTERN.match(s[:16]))


def _parse_args(argv: list[str]) -> tuple[str, str, list[str], list[str], dict]:
    """
    解析 argv：
    - 前两个非 flag 为 origin, destination；
    - --departure-time start end（必填），--arrival-time start end（可选）；
    - --max-price、--sort-by 进入 options。
    返回 (origin, destination, departure_time_range, arrival_time_range, options)。
    """
    args = [a for a in argv if a != ""]
    positionals = []
    options = {}
    departure_range: list[str] = []
    arrival_range: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:].strip().lower()
            if key == "departure-time":
                # 取两个值作为 [start, end]
                if i + 2 <= len(args) and not args[i + 1].startswith("--") and not args[i + 2].startswith("--"):
                    departure_range = [args[i + 1].strip(), args[i + 2].strip()]
                    i += 3
                    continue
                elif i + 1 < len(args) and not args[i + 1].startswith("--") and ENABLE_NLP_TIME_RANGE:
                    # 仅当开启 NLP 时接受单值（自然语言）
                    departure_range = [args[i + 1].strip()]
                    i += 2
                    continue
            elif key == "arrival-time":
                if i + 2 <= len(args) and not args[i + 1].startswith("--") and not args[i + 2].startswith("--"):
                    arrival_range = [args[i + 1].strip(), args[i + 2].strip()]
                    i += 3
                    continue
            elif key in OPTION_KEYS and i + 1 < len(args) and not args[i + 1].startswith("--"):
                val = args[i + 1].strip()
                opt_key = OPTION_KEYS[key]
                if opt_key == "max_price":
                    try:
                        options[opt_key] = float(val)
                    except ValueError:
                        options[opt_key] = val
                else:
                    options[opt_key] = val
                i += 2
                continue
            i += 1
            continue
        positionals.append(a)
        i += 1
    origin = (positionals[0] or "").strip() if len(positionals) > 0 else ""
    destination = (positionals[1] or "").strip() if len(positionals) > 1 else ""
    return origin, destination, departure_range, arrival_range, options


def _nlp_to_time_range(single_value: str) -> tuple[str, str] | None:
    """当 ENABLE_NLP_TIME_RANGE 时，将自然语言转为 [start, end] 的 yyyy-MM-dd HH:mm。"""
    if not single_value or _is_standard_datetime(single_value):
        return None
    try:
        from normalize_date import normalize_date
        dt = normalize_date(single_value, time_base=datetime.now())
        date_str = (dt.get("date") or "").strip()
        if not date_str or len(date_str) < 10:
            return None
        return (f"{date_str} 00:00", f"{date_str} 23:59")
    except Exception:
        return None


def main() -> None:
    _ensure_utf8_io()
    origin, destination, departure_range, arrival_range, options = _parse_args(sys.argv[1:])

    # 参数不足时走澄清流程
    missing = []
    if not origin:
        missing.append("origin")
    if not destination:
        missing.append("destination")
    if not departure_range:
        missing.append("departure_time_range")
    elif len(departure_range) == 1 and ENABLE_NLP_TIME_RANGE:
        resolved = _nlp_to_time_range(departure_range[0])
        if resolved:
            departure_range = list(resolved)
        else:
            missing.append("departure_time_range")
    elif len(departure_range) == 2 and (not _is_standard_datetime(departure_range[0]) or not _is_standard_datetime(departure_range[1])):
        missing.append("departure_time_range")

    if missing:
        msg = "请提供："
        if "origin" in missing:
            msg += "出发地；"
        if "destination" in missing:
            msg += "目的地；"
        if "departure_time_range" in missing:
            msg += "出发时间范围，格式为 yyyy-MM-dd HH:mm 的 [开始, 结束]。"
        _out({
            "success": False,
            "clarification_needed": True,
            "missing": missing,
            "message": msg.strip(),
            "error": msg.strip(),
        })
        sys.exit(0)

    # 从出发时间范围取日期供 API 使用
    dep_start = departure_range[0].strip()[:16]
    departure_date = dep_start[:10]  # yyyy-MM-dd

    from location_to_iata import get_data_dir, load_maps, load_airport_map, load_nearest_airport_map, resolve_iata
    from query_flight_api import query
    from filter_sort_flights import filter_and_sort

    data_dir = get_data_dir()
    if not (data_dir / "city_map.json").exists():
        err = f"数据目录无效或缺少 city_map.json: {data_dir}"
        _out({"success": False, "error": err, "message": err})
        sys.exit(1)

    city_map, province_map = load_maps(data_dir)
    airport_map = load_airport_map(data_dir) or None
    nearest_airport_map = load_nearest_airport_map(data_dir) or None

    o = resolve_iata(origin, city_map, province_map, airport_map, nearest_airport_map)
    d = resolve_iata(destination, city_map, province_map, airport_map, nearest_airport_map)

    if not o.get("iata"):
        err = f"无法解析出发地「{origin}」，请检查输入或更换表述。"
        _out({"success": False, "error": err, "message": err})
        sys.exit(1)
    if not d.get("iata"):
        err = f"无法解析目的地「{destination}」，请检查输入或更换表述。"
        _out({"success": False, "error": err, "message": err})
        sys.exit(1)

    dep, arr = o["iata"], d["iata"]
    resp = query(departure=dep, arrival=arr, departure_date=departure_date, max_segments=DEFAULT_MAX_SEGMENTS)

    if resp.get("error_code") != 0:
        err = resp.get("error") or resp.get("reason") or "API 请求失败"
        _out({
            "success": False,
            "error": err,
            "message": err,
        })
        sys.exit(1)

    result = resp.get("result", {})
    info = result.get("flightInfo") or []

    # 合并时间范围与其它 options 做筛选与排序
    filter_options = dict(options)
    filter_options["departure_time_range"] = departure_range
    if arrival_range and len(arrival_range) >= 2 and _is_standard_datetime(arrival_range[0]) and _is_standard_datetime(arrival_range[1]):
        filter_options["arrival_time_range"] = arrival_range
    if filter_options:
        info = filter_and_sort(info, filter_options)
        result["flightInfo"] = info
        result["flightCount"] = len(info)

    # 按 config 限制输出航班数量（-1 表示不限制）
    out_info = result.get("flightInfo") or []
    if MAX_OUTPUT_FLIGHTS >= 0 and len(out_info) > MAX_OUTPUT_FLIGHTS:
        result["flightInfo"] = out_info[:MAX_OUTPUT_FLIGHTS]
        result["flightCount"] = MAX_OUTPUT_FLIGHTS

    flight_count = len(result.get("flightInfo") or [])
    out_payload = {"success": True, "result": result}
    if flight_count == 0:
        out_payload["message"] = "该日期与航线上暂无符合条件的航班，可尝试调整出发日期、放宽筛选条件或更换航线。"
        out_payload["reason"] = out_payload["message"]
    _out(out_payload)


if __name__ == "__main__":
    main()
