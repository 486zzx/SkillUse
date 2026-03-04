#!/usr/bin/env python3
"""
自然语言时间 → 单日日期(YYYY-MM-DD) + 时间段(HH:MM)。
使用 jionlp.parse_time 解析「明天」「后天下午五点后」「五点后」等，并归一为「仅当天」的时间段（如 17:00~23:59）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _parse_with_jionlp(text: str, time_base: float | datetime) -> dict[str, Any] | None:
    """调用 jionlp.parse_time，返回原始解析结果。time_base 为 time.time() 或 datetime。"""
    try:
        import jionlp as jio
    except ImportError:
        return None
    base_ts = time_base.timestamp() if isinstance(time_base, datetime) else time_base
    try:
        return jio.parse_time(text.strip(), time_base=base_ts)
    except Exception:
        return None


def _timestamps_to_single_day_range(
    start_iso: str, end_iso: str
) -> tuple[str, str, str]:
    """
    将起止时间归一为「单日」的日期 + 时间范围。
    返回 (date_yyyy_mm_dd, time_min_HHMM, time_max_HHMM)，时间限制在当日 00:00~23:59。
    """
    def parse_iso(s: str) -> tuple[str, int, int]:
        """解析 'YYYY-MM-DD HH:MM:SS' / 'YYYY-MM-DDTHH:MM:SS' / 'YYYY-MM-DD'，返回 (date, 当日分钟)。"""
        s = (s or "").strip()
        if not s or len(s) < 10:
            return "", 0, 0
        date_part = s[:10]
        minutes = 0
        import re as _re
        time_m = _re.search(r"T?\s*(\d{1,2}):(\d{2})", s[10:])
        if time_m:
            minutes = int(time_m.group(1)) * 60 + int(time_m.group(2))
        return date_part, minutes, minutes  # (date, 当日分钟, 同值供 end 用)

    start_date, start_min, _ = parse_iso(start_iso)
    end_date, _, end_min = parse_iso(end_iso)
    if not start_date:
        return "", "00:00", "23:59"

    # 只认「当天」：以 start 的日期为准，起止时间限制在该日内；若 end 跨天则截断到 23:59
    day_end_min = 24 * 60 - 1  # 23:59
    t_min = max(0, min(start_min, day_end_min))
    t_max = day_end_min if start_date != end_date else min(day_end_min, end_min)
    t_max = max(t_min, min(t_max, day_end_min))

    def min_to_hhmm(m: int) -> str:
        m = max(0, min(m, 24 * 60 - 1))
        h, mi = m // 60, m % 60
        return f"{h:02d}:{mi:02d}"
    return start_date, min_to_hhmm(t_min), min_to_hhmm(t_max)


def _extract_time_list(res: dict[str, Any]) -> list[str] | None:
    """从 jionlp 结果中取出时间列表 [start_iso, end_iso]。支持 time_span / time_point / time_period。"""
    t = res.get("time")
    if isinstance(t, list) and len(t) >= 1:
        first = t[0]
        if isinstance(first, str) and len(first) >= 10:
            if len(t) >= 2 and isinstance(t[1], str):
                return [first, t[1]]
            return [first, first[:10] + " 23:59:59"]
        if isinstance(first, dict):
            point = first.get("point") or first
            if isinstance(point, dict) and "time" in point:
                pt = point["time"]
                if isinstance(pt, list) and len(pt) >= 2:
                    return [pt[0], pt[1]]
                if isinstance(pt, list) and len(pt) >= 1:
                    return [pt[0], pt[0][:10] + " 23:59:59"]
    if isinstance(t, dict):
        pt = t.get("point", {}).get("time") if isinstance(t.get("point"), dict) else t.get("time")
        if isinstance(pt, list) and len(pt) >= 2:
            return [pt[0], pt[1]]
        if isinstance(pt, list) and len(pt) >= 1:
            return [pt[0], pt[0][:10] + " 23:59:59"]
    return None


def parse_departure_time(
    text: str, time_base: datetime | None = None
) -> dict[str, str] | None:
    """
    解析出发时间（含日期+时段），归一为单日 + 时间段。
    例如：「明天」→ 明天 00:00~23:59；「后天下午五点后」→ 后天 17:00~23:59。
    返回 {"date": "YYYY-MM-DD", "time_min": "HH:MM", "time_max": "HH:MM"}，失败返回 None。
    """
    text = (text or "").strip()
    if not text:
        return None
    base = time_base or datetime.now()
    res = _parse_with_jionlp(text, base)
    if res:
        time_list = _extract_time_list(res)
        if time_list:
            date, tm_min, tm_max = _timestamps_to_single_day_range(time_list[0], time_list[1])
            if date:
                return {"date": date, "time_min": tm_min, "time_max": tm_max}
    return None


def parse_arrival_time(
    text: str, time_base: datetime | None = None, reference_date: str | None = None
) -> dict[str, str] | None:
    """
    解析到达时间（仅时段），归一为当日时间范围。
    例如：「五点后」→ 17:00~23:59；「晚上前」→ 00:00~18:00。
    reference_date 若提供则用于解析相对表述，否则用 time_base 的日期。
    返回 {"time_min": "HH:MM", "time_max": "HH:MM"}，失败返回 None。
    """
    text = (text or "").strip()
    if not text:
        return None
    base = time_base or datetime.now()
    res = _parse_with_jionlp(text, base)
    if res:
        time_list = _extract_time_list(res)
        if time_list:
            date, tm_min, tm_max = _timestamps_to_single_day_range(time_list[0], time_list[1])
            if date:
                return {"time_min": tm_min, "time_max": tm_max}
    return None
