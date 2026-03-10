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
from datetime import datetime
from pathlib import Path

from config import DATETIME_FMT


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


def _parse_datetime(date_str: str, time_str: str) -> datetime | None:
    """将 departureDate + departureTime 或 arrivalDate + arrivalTime 拼成 datetime。"""
    d = (date_str or "").strip()
    t = (time_str or "").strip()
    if not d:
        return None
    if not t or len(t) < 4:
        t = "00:00"
    elif len(t) == 4 and ":" not in t:
        t = t[:2] + ":" + t[2:]
    s = f"{d} {t}"
    if len(s) < 16:
        s = s + " 00:00"[: 16 - len(s)]
    try:
        return datetime.strptime(s[:16], DATETIME_FMT)
    except ValueError:
        return None


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

    # 出发时间范围 [start, end]，格式 yyyy-MM-dd HH:mm
    if "departure_time_range" in options and options["departure_time_range"]:
        r = options["departure_time_range"]
        if isinstance(r, (list, tuple)) and len(r) >= 2:
            try:
                start_dt = datetime.strptime(str(r[0]).strip()[:16], DATETIME_FMT)
                end_dt = datetime.strptime(str(r[1]).strip()[:16], DATETIME_FMT)
            except ValueError:
                pass
            else:
                out = [
                    f
                    for f in out
                    if start_dt <= (_parse_datetime(f.get("departureDate"), f.get("departureTime")) or datetime.min) <= end_dt
                ]

    # 到达时间范围 [start, end]，格式 yyyy-MM-dd HH:mm
    if "arrival_time_range" in options and options["arrival_time_range"]:
        r = options["arrival_time_range"]
        if isinstance(r, (list, tuple)) and len(r) >= 2:
            try:
                start_dt = datetime.strptime(str(r[0]).strip()[:16], DATETIME_FMT)
                end_dt = datetime.strptime(str(r[1]).strip()[:16], DATETIME_FMT)
            except ValueError:
                pass
            else:
                out = [
                    f
                    for f in out
                    if start_dt <= (_parse_datetime(f.get("arrivalDate"), f.get("arrivalTime")) or datetime.min) <= end_dt
                ]

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
