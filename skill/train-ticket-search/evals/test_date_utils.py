"""date_utils 单元测试。"""
from datetime import datetime

import pytest

from date_utils import normalize_date, normalize_date_string


def test_normalize_date_today():
    base = datetime(2025, 12, 20)
    r = normalize_date("今天", base)
    assert r["date"] == "2025-12-20"
    assert r["source"] in ("simple", "jio")


def test_normalize_date_tomorrow():
    base = datetime(2025, 12, 20)
    r = normalize_date("明天", base)
    assert r["date"] == "2025-12-21"


def test_normalize_date_day_after():
    base = datetime(2025, 12, 20)
    r = normalize_date("后天", base)
    assert r["date"] == "2025-12-22"


def test_normalize_date_iso():
    base = datetime(2025, 12, 20)
    r = normalize_date("2025-12-25", base)
    assert r["date"] == "2025-12-25"


def test_normalize_date_slash():
    base = datetime(2025, 12, 20)
    r = normalize_date("2025/12/25", base)
    assert r["date"] == "2025-12-25"


def test_normalize_date_n_month_day():
    # base 在 1 月时，“3月5号”应为当年 3 月 5 日
    base = datetime(2025, 1, 15)
    r = normalize_date("3月5号", base)
    assert r["date"] == "2025-03-05"


def test_normalize_date_n_month_day_same_year():
    base = datetime(2025, 1, 1)
    r = normalize_date("12月25日", base)
    assert r["date"] == "2025-12-25"


def test_normalize_date_fail():
    base = datetime(2025, 12, 20)
    r = normalize_date("不是日期", base)
    assert r["date"] == ""
    assert r["source"] == "fail"
    assert r["raw"] == "不是日期"


def test_normalize_date_string():
    base = datetime(2025, 12, 20)
    assert normalize_date_string("明天", base) == "2025-12-21"
    assert normalize_date_string("", base) == ""
    assert normalize_date_string("无效", base) == ""
