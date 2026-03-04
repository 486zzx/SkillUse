#!/usr/bin/env python3
"""
对 flightInfo 列表做筛选与排序。
输入：命令行长参数（整段 JSON）或 --file <path>。格式 { "flightInfo": [...], "options": { "max_price": 2000, "sort_by": "price_asc" } }，options 可选。
输出：筛选并排序后的 flightInfo 列表 JSON。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _ensure_utf8_io() -> None:
    """避免 Windows 控制台 GBK 导致 print 报错或乱码，强制 stdout/stderr 使用 UTF-8。"""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _parse_time(s: str) -> int:
    """HH:MM -> 分钟数便于比较"""
    if not s:
        return 0
    m = re.match(r"(\d{1,2}):(\d{2})", str(s))
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return 0


def _parse_duration(s: str) -> int:
    """08h00m -> 分钟数"""
    if not s:
        return 0
    s = str(s).strip()
    total = 0
    for part in re.findall(r"(\d+)h", s):
        total += int(part) * 60
    for part in re.findall(r"(\d+)m", s):
        total += int(part)
    return total


def filter_and_sort(flight_info: list[dict], options: dict | None = None) -> list[dict]:
    options = options or {}
    out = list(flight_info)

    # 筛选
    if "max_price" in options and options["max_price"] is not None:
        try:
            mx = float(options["max_price"])
            out = [f for f in out if (f.get("ticketPrice") or 0) <= mx]
        except (TypeError, ValueError):
            pass

    if "min_departure_time" in options and options["min_departure_time"]:
        t_min = _parse_time(options["min_departure_time"])
        out = [f for f in out if _parse_time(f.get("departureTime") or "") >= t_min]

    if "max_departure_time" in options and options["max_departure_time"]:
        t_max = _parse_time(options["max_departure_time"])
        out = [f for f in out if _parse_time(f.get("departureTime") or "") <= t_max]

    if "equipment_contains" in options and options["equipment_contains"]:
        kw = str(options["equipment_contains"]).strip()
        out = [f for f in out if kw in str(f.get("equipment") or "")]

    # 排序
    sort_by = (options.get("sort_by") or "").strip().lower()
    if sort_by == "price_asc":
        out.sort(key=lambda f: (f.get("ticketPrice") or 0))
    elif sort_by == "price_desc":
        out.sort(key=lambda f: -(f.get("ticketPrice") or 0))
    elif sort_by == "departure_asc":
        out.sort(key=lambda f: (f.get("departureDate") or "", f.get("departureTime") or ""))
    elif sort_by == "departure_desc":
        out.sort(key=lambda f: (f.get("departureDate") or "", f.get("departureTime") or ""), reverse=True)
    elif sort_by == "duration_asc":
        out.sort(key=lambda f: _parse_duration(f.get("duration") or ""))

    return out


def main() -> None:
    _ensure_utf8_io()
    if "--file" in sys.argv:
        i = sys.argv.index("--file")
        try:
            path = sys.argv[i + 1]
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (IndexError, OSError, json.JSONDecodeError) as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
    elif sys.argv[1:]:
        raw = " ".join(sys.argv[1:]).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
    else:
        print(json.dumps({"error": "缺少输入：请将 JSON 作为命令行参数传入，或使用 --file <path>"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    flight_info = data.get("flightInfo", data) if isinstance(data, dict) else data
    if not isinstance(flight_info, list):
        flight_info = []
    options = data.get("options", {}) if isinstance(data, dict) else {}

    result = filter_and_sort(flight_info, options)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
