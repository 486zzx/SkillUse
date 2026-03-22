#!/usr/bin/env python3
"""
时间解析（仅标准格式）：yyyy-MM-dd HH:mm 范围、数组 ["起始","终止"]、单日期 yyyy-MM-dd。
自然语言（如「明天」「五点后」）已移至 reserve/time-conversion，主流程默认时间输入已正确。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

# 标准范围格式：yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm（起止用逗号分隔）
_STANDARD_RANGE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})\s*,\s*(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})\s*$"
)
# 单日期或单日期+时间：yyyy-MM-dd 或 yyyy-MM-dd HH:mm
_SINGLE_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}):(\d{2}))?\s*$")


def _hhmm(d: int, h: int, m: int) -> str:
    """将日、时、分转为 HH:MM（仅时间部分）。"""
    h, m = int(h), int(m)
    h = max(0, min(23, h))
    m = max(0, min(59, m))
    return f"{h:02d}:{m:02d}"


def _parse_single_date_or_datetime(s: str) -> tuple[str, str, str] | None:
    """
    解析单日期或「日期+时间」，返回 (date_yyyy_mm_dd, time_min_HHMM, time_max_HHMM)。
    仅有日期时视为全天 00:00~23:59；有 HH:mm 时视为该时刻~23:59。
    """
    s = (s or "").strip()
    if not s or len(s) < 10:
        return None
    m = _SINGLE_DATE_RE.match(s[:19] if len(s) > 10 else s)
    if not m:
        return None
    date_part = m.group(1)
    if m.lastindex >= 3 and m.group(2) is not None:
        h, mi = int(m.group(2)), int(m.group(3))
        time_min = _hhmm(0, h, mi)
        time_max = "23:59"
    else:
        time_min = "00:00"
        time_max = "23:59"
    return date_part, time_min, time_max


def _normalize_departure_input(value: list[str] | str) -> str | None:
    """
    将「数组或字符串」的出发时间统一成标准范围字符串 "yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm"。
    """
    if isinstance(value, list):
        if len(value) == 2 and value[0] and value[1]:
            return f"{str(value[0]).strip()}, {str(value[1]).strip()}"
        if len(value) == 1 and value[0]:
            single = _parse_single_date_or_datetime(str(value[0]).strip())
            if single:
                return f"{single[0]} {single[1]}, {single[0]} {single[2]}"
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def parse_departure_time_array_or_string(
    value: list[str] | str,
    time_base: datetime | None = None,
    allow_natural_language: bool = False,
) -> dict[str, str] | None:
    """
    解析出发时间（仅标准格式）：
    - 数组 ["起始时间", "终止时间"] 或 ["日期"]（单日期为全天）
    - 字符串形式的 JSON 数组、或 "yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm" 或单日期 "yyyy-MM-dd"
    返回 {"date": "YYYY-MM-DD", "time_min": "HH:MM", "time_max": "HH:MM"}，失败返回 None。
    allow_natural_language 保留兼容，当前未使用（自然语言逻辑在 reserve/time-conversion）。
    """
    if isinstance(value, str):
        s = value.strip()
        if len(s) >= 2 and s.startswith("[") and s.endswith("]"):
            s_normal = s.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
            try:
                arr = json.loads(s_normal)
                if isinstance(arr, list) and len(arr) >= 1:
                    value = arr
            except (json.JSONDecodeError, ValueError, TypeError):
                match = re.match(r'\[\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*\]', s)
                if match:
                    value = [match.group(1).strip(), match.group(2).strip()]
    raw = _normalize_departure_input(value) if isinstance(value, list) else (value.strip() if isinstance(value, str) else None)
    if not raw:
        return None
    parsed = parse_standard_departure_range(raw)
    if parsed:
        return parsed
    single = _parse_single_date_or_datetime(raw)
    if single:
        return {"date": single[0], "time_min": single[1], "time_max": single[2]}
    return None


def parse_arrival_time_array_or_string(
    value: list[str] | str | None,
    time_base: datetime | None = None,
    allow_natural_language: bool = False,
) -> dict[str, str] | None:
    """
    解析到达时间（仅标准格式）。
    allow_natural_language 保留兼容，当前未使用。
    """
    if value is None:
        return None
    if isinstance(value, list):
        if len(value) == 0:
            return None
        if len(value) == 2 and value[0] and value[1]:
            raw = f"{str(value[0]).strip()}, {str(value[1]).strip()}"
        elif len(value) == 1 and value[0]:
            single = _parse_single_date_or_datetime(str(value[0]).strip())
            if single:
                return {"time_min": single[1], "time_max": single[2]}
            return None
        else:
            return None
    else:
        raw = (value or "").strip()
    if not raw:
        return None
    parsed = parse_standard_arrival_range(raw)
    if parsed:
        return parsed
    single = _parse_single_date_or_datetime(raw)
    if single:
        return {"time_min": single[1], "time_max": single[2]}
    return None


def parse_standard_departure_range(text: str) -> dict[str, str] | None:
    """
    仅解析标准格式：yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm。
    返回 {"date": "YYYY-MM-DD", "time_min": "HH:MM", "time_max": "HH:MM"}，失败返回 None。
    """
    text = (text or "").strip()
    if not text:
        return None
    m = _STANDARD_RANGE_RE.match(text)
    if not m:
        return None
    date1, hour1, min1 = m.group(1), int(m.group(2)), int(m.group(3))
    date2, hour2, min2 = m.group(4), int(m.group(5)), int(m.group(6))
    time_min = _hhmm(0, hour1, min1)
    if date1 != date2:
        time_max = "23:59"
    else:
        time_max = _hhmm(0, hour2, min2)
    return {"date": date1, "time_min": time_min, "time_max": time_max}


def parse_standard_arrival_range(text: str) -> dict[str, str] | None:
    """
    仅解析标准格式：yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm。
    返回 {"time_min": "HH:MM", "time_max": "HH:MM"}，失败返回 None。
    """
    text = (text or "").strip()
    if not text:
        return None
    m = _STANDARD_RANGE_RE.match(text)
    if not m:
        return None
    date1, hour1, min1 = m.group(1), int(m.group(2)), int(m.group(3))
    date2, hour2, min2 = m.group(4), int(m.group(5)), int(m.group(6))
    return {"time_min": _hhmm(0, hour1, min1), "time_max": _hhmm(0, hour2, min2)}
