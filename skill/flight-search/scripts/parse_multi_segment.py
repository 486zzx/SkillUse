#!/usr/bin/env python3
"""
多段行程标准化：将多段（出发、到达、日期）转为 IATA + yyyy-mm-dd。
输入：[{"origin":"上海","destination":"西安","date":"明天"}, ...]
输出：[{"departure":"SHA","arrival":"SIA","departureDate":"2026-03-02"}, ...]
依赖同目录 location_to_iata 与 normalize_date。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


def _ensure_utf8_io() -> None:
    """避免 Windows 控制台 GBK 导致 print 报错或乱码，强制 stdout/stderr 使用 UTF-8。"""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# 同目录
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from location_to_iata import get_data_dir, load_maps, load_airport_map, load_nearest_airport_map, resolve_iata
from normalize_date import normalize_date as _normalize_date


def parse_segments(segments: list[dict], time_base: datetime | None = None) -> list[dict]:
    """
    segments: [{"origin": str, "destination": str, "date": str}, ...]
    return: [{"departure": IATA, "arrival": IATA, "departureDate": yyyy-mm-dd}, ...]
    """
    base = time_base or datetime.now()
    data_dir = get_data_dir()
    city_map, province_map = load_maps(data_dir)
    airport_map = load_airport_map(data_dir) or None
    nearest_airport_map = load_nearest_airport_map(data_dir) or None

    out = []
    for seg in segments:
        origin = (seg.get("origin") or seg.get("origin_raw") or "").strip()
        dest = (seg.get("destination") or seg.get("dest_raw") or "").strip()
        date_raw = (seg.get("date") or seg.get("date_raw") or "").strip()

        o = resolve_iata(origin, city_map, province_map, airport_map, nearest_airport_map)
        d = resolve_iata(dest, city_map, province_map, airport_map, nearest_airport_map)
        dt = _normalize_date(date_raw, base)

        if not o["iata"] or not d["iata"]:
            out.append({
                "departure": o["iata"],
                "arrival": d["iata"],
                "departureDate": dt["date"],
                "error": f"无法解析地点: {origin} -> {dest}",
            })
            continue
        if not dt["date"]:
            out.append({
                "departure": o["iata"],
                "arrival": d["iata"],
                "departureDate": "",
                "error": f"无法解析日期: {date_raw}",
            })
            continue
        out.append({
            "departure": o["iata"],
            "arrival": d["iata"],
            "departureDate": dt["date"],
        })
    return out


def main() -> None:
    _ensure_utf8_io()
    if not sys.argv[1:]:
        print(json.dumps({"error": "缺少输入：请将 JSON 作为命令行参数传入"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    raw = " ".join(sys.argv[1:]).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    if isinstance(data, dict):
        data = [data]
    result = parse_segments(data)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
