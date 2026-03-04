"""filter_sort 单元测试。"""
import pytest

from filter_sort import (
    filter_by_train_type,
    filter_by_departure_time,
    filter_by_arrival_time,
    sort_trains,
    SORT_OPTIONS,
    time_range_to_api_name,
)


@pytest.fixture
def sample_trains():
    return [
        {"train_no": "G101", "departure_time": "10:00", "arrival_time": "14:00", "duration": "4h00m", "seat_types": [{"price": 500}]},
        {"train_no": "D201", "departure_time": "08:00", "arrival_time": "13:00", "duration": "5h00m", "seat_types": [{"price": 300}]},
        {"train_no": "K301", "departure_time": "22:00", "arrival_time": "08:00", "duration": "10h00m", "seat_types": [{"price": 100}]},
    ]


def test_filter_by_train_type_empty(sample_trains):
    out = filter_by_train_type(sample_trains, None)
    assert len(out) == 3
    out = filter_by_train_type(sample_trains, [])
    assert len(out) == 3


def test_filter_by_train_type_g_only(sample_trains):
    out = filter_by_train_type(sample_trains, ["G"])
    assert len(out) == 1
    assert out[0]["train_no"] == "G101"


def test_filter_by_train_type_g_and_d(sample_trains):
    out = filter_by_train_type(sample_trains, ["G", "D"])
    assert len(out) == 2
    nos = {t["train_no"] for t in out}
    assert nos == {"G101", "D201"}


def test_sort_trains_price_asc(sample_trains):
    out = sort_trains(sample_trains, "price_asc")
    assert out[0]["train_no"] == "K301"
    assert out[-1]["train_no"] == "G101"


def test_sort_trains_price_desc(sample_trains):
    out = sort_trains(sample_trains, "price_desc")
    assert out[0]["train_no"] == "G101"


def test_sort_trains_departure_asc(sample_trains):
    out = sort_trains(sample_trains, "departure_asc")
    assert out[0]["departure_time"] == "08:00"
    assert out[-1]["departure_time"] == "22:00"


def test_sort_trains_departure_desc(sample_trains):
    out = sort_trains(sample_trains, "departure_desc")
    assert out[0]["departure_time"] == "22:00"


def test_sort_trains_duration_asc(sample_trains):
    out = sort_trains(sample_trains, "duration_asc")
    assert out[0]["duration"] == "4h00m"
    assert out[-1]["duration"] == "10h00m"


def test_sort_trains_none_unchanged(sample_trains):
    out = sort_trains(sample_trains, None)
    assert out == sample_trains


def test_sort_trains_invalid_unchanged(sample_trains):
    out = sort_trains(sample_trains, "invalid")
    assert out == sample_trains


def test_filter_by_departure_time_range(sample_trains):
    # 上午 = [06:00, 12:00)，只有 08:00 和 10:00 在范围内
    out = filter_by_departure_time(sample_trains, range_name="上午")
    assert len(out) == 2
    assert all(_time_to_minutes(t["departure_time"]) >= 6 * 60 for t in out)
    assert all(_time_to_minutes(t["departure_time"]) < 12 * 60 for t in out)


def test_filter_by_departure_time_min_max(sample_trains):
    # 出发不早于 09:00、不晚于 11:00
    out = filter_by_departure_time(sample_trains, time_min="09:00", time_max="11:00")
    assert len(out) == 1
    assert out[0]["departure_time"] == "10:00"


def test_filter_by_arrival_time_range(sample_trains):
    # 下午到达 = [12:00, 18:00)
    out = filter_by_arrival_time(sample_trains, range_name="下午")
    assert len(out) == 2  # 14:00, 13:00
    assert all(_time_to_minutes(t["arrival_time"]) >= 12 * 60 for t in out)
    assert all(_time_to_minutes(t["arrival_time"]) < 18 * 60 for t in out)


def test_filter_by_arrival_time_max(sample_trains):
    # 18:00 前到达
    out = filter_by_arrival_time(sample_trains, time_max="18:00")
    assert len(out) == 3
    assert all(_time_to_minutes(t["arrival_time"]) <= 18 * 60 for t in out)


# --- time_range_to_api_name：全天不传时段，避免误传凌晨导致空结果 ---
def test_time_range_to_api_name_full_day_returns_none():
    """全天 00:00~23:59 必须返回 None，不能返回「凌晨」导致 API 只查 0~6 点。"""
    assert time_range_to_api_name("00:00", "23:59") is None


def test_time_range_to_api_name_morning_returns_上午():
    """上午时段 06:00~11:59 应返回「上午」。"""
    assert time_range_to_api_name("06:00", "11:59") == "上午"


def test_time_range_to_api_name_afternoon_returns_下午():
    """下午 12:00~17:59 应返回「下午」。"""
    assert time_range_to_api_name("12:00", "17:59") == "下午"


def test_time_range_to_api_name_night_returns_晚上():
    """晚上 18:00~23:59 应返回「晚上」。"""
    assert time_range_to_api_name("18:00", "23:59") == "晚上"


def test_time_range_to_api_name_dawn_returns_凌晨():
    """凌晨 00:00~05:59 应返回「凌晨」。"""
    assert time_range_to_api_name("00:00", "05:59") == "凌晨"


def test_time_range_to_api_name_empty_or_none_returns_none():
    """空或 None 返回 None。"""
    assert time_range_to_api_name("", "23:59") is None
    assert time_range_to_api_name("06:00", None) is None


def _time_to_minutes(t):
    import re
    if not t:
        return 0
    m = re.match(r"(\d{1,2}):(\d{2})", str(t).strip())
    return (int(m.group(1)) * 60 + int(m.group(2))) if m else 0
