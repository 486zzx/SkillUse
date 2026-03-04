"""time_utils 单元测试：自然语言时间 → 单日日期 + 时间段（仅 jionlp，无 fallback）。"""
from datetime import datetime

import pytest

pytest.importorskip("jionlp")

from time_utils import parse_departure_time, parse_arrival_time


# --- 出发时间解析 ---
def test_parse_departure_tomorrow():
    base = datetime(2025, 3, 4, 10, 0)
    r = parse_departure_time("明天", base)
    assert r is not None
    assert r["date"] == "2025-03-05"
    assert "time_min" in r and "time_max" in r


def test_parse_departure_today():
    """「今天」应解析为 base 当天，时间范围合理。"""
    base = datetime(2025, 3, 4)
    r = parse_departure_time("今天", base)
    assert r is not None
    assert r["date"] == "2025-03-04"
    assert "time_min" in r and "time_max" in r


def test_parse_departure_day_after_tomorrow():
    """「后天」应解析为 base+2 天。"""
    base = datetime(2025, 3, 4)
    r = parse_departure_time("后天", base)
    assert r is not None
    assert r["date"] == "2025-03-06"


def test_parse_departure_iso_date():
    base = datetime(2025, 3, 4)
    r = parse_departure_time("2025-12-21", base)
    assert r is not None
    assert r["date"] == "2025-12-21"
    assert r.get("time_min") == "00:00"
    assert r.get("time_max") == "23:59"


def test_parse_departure_empty_and_none():
    assert parse_departure_time("", None) is None
    assert parse_departure_time("  ", datetime(2025, 1, 1)) is None


def test_parse_departure_result_has_required_keys():
    """返回结构必须包含 date, time_min, time_max。"""
    base = datetime(2025, 3, 4)
    r = parse_departure_time("明天", base)
    assert r is not None
    assert "date" in r and "time_min" in r and "time_max" in r
    assert len(r["date"]) == 10 and r["date"][4] == "-" and r["date"][7] == "-"


# --- 到达时间解析 ---
def test_parse_arrival_empty():
    assert parse_arrival_time("", None) is None


def test_parse_arrival_after_five():
    """「五点后」由 jionlp 解析，可能有 time_min/time_max。"""
    base = datetime(2025, 3, 4)
    r = parse_arrival_time("五点后", base)
    assert r is not None
    assert "time_min" in r and "time_max" in r
    assert r["time_min"] <= r["time_max"]


def test_parse_arrival_result_has_time_keys():
    """到达时间解析返回 time_min, time_max。"""
    base = datetime(2025, 3, 4)
    r = parse_arrival_time("下午", base)
    if r:
        assert "time_min" in r and "time_max" in r


# 直接采用 jionlp 解析结果，不做年份修正
