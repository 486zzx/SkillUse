#!/usr/bin/env python3
"""
自然语言日期 → yyyy-mm-dd。
支持：今天/明天/后天、N月M日、yyyy-mm-dd。
可选依赖 jionlp 以支持更复杂表述（与 flight-search 的 normalize_date 逻辑一致）。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta


def _parse_simple(text: str, base: datetime) -> str | None:
    """简单规则：今天/明天/后天、N月M日、yyyy-mm-dd。"""
    text = text.strip()
    if not text:
        return None

    for delta, kw in [(0, "今天"), (1, "明天"), (2, "后天")]:
        if kw in text or text == kw:
            d = base + timedelta(days=delta)
            return d.strftime("%Y-%m-%d")

    week_cn = ["一", "二", "三", "四", "五", "六", "日"]
    for wd, cn in enumerate(week_cn):
        if text == "下周" + cn or text == "下礼拜" + cn:
            days_ahead = (wd - base.weekday() + 7) % 7
            if days_ahead == 0:
                days_ahead = 7
            d = base + timedelta(days=days_ahead)
            return d.strftime("%Y-%m-%d")

    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = datetime(y, mo, d)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    m = re.search(r"(\d{1,2})月(\d{1,2})[日号]", text)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        y = base.year
        try:
            dt = datetime(y, mo, d)
            if dt < base:
                dt = datetime(y + 1, mo, d)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def _parse_with_jio(text: str, time_base: datetime) -> str | None:
    try:
        import jionlp as jio
    except ImportError:
        return None
    try:
        base_ts = time_base.timestamp()
        res = jio.parse_time(text, time_base=base_ts)
    except Exception:
        return None
    if not res or "time" not in res:
        return None
    t = res["time"]
    if isinstance(t, list) and len(t) >= 1:
        s = t[0]
        if isinstance(s, str) and len(s) >= 10:
            return s[:10]
    return None


def normalize_date(text: str, time_base: datetime | None = None) -> dict:
    """
    解析单个日期字符串，返回 {"date": "yyyy-mm-dd", "source": "jio|simple|fail", "raw": "..."}
    若解析失败，date 为空字符串，source 为 "fail"。
    """
    base = time_base or datetime.now()
    raw = text.strip()

    out = _parse_with_jio(raw, base)
    if out:
        return {"date": out, "source": "jio", "raw": raw}

    out = _parse_simple(raw, base)
    if out:
        return {"date": out, "source": "simple", "raw": raw}

    return {"date": "", "source": "fail", "raw": raw}


def normalize_date_string(text: str, time_base: datetime | None = None) -> str:
    """解析日期并只返回 yyyy-mm-dd，失败返回空字符串。"""
    r = normalize_date(text, time_base)
    return r.get("date", "") or ""
