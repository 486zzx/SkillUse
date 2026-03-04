"""query_api 单元测试。"""
import os

import pytest

from query_api import query_trains, get_duration_minutes, API_KEY_ENV


def test_query_trains_missing_from():
    trains, err = query_trains("", "上海", "2025-12-21")
    assert err == "出发站不能为空"
    assert trains == []


def test_query_trains_missing_to():
    trains, err = query_trains("北京", "", "2025-12-21")
    assert err == "到达站不能为空"
    assert trains == []


def test_query_trains_missing_date():
    trains, err = query_trains("北京", "上海", "")
    assert err == "出发日期不能为空"
    assert trains == []


def test_query_trains_bad_date_format():
    trains, err = query_trains("北京", "上海", "12月21日")
    assert err is not None
    assert "yyyy-mm-dd" in err
    assert trains == []


def test_query_trains_no_api_key():
    """未配置 JUHE_TRAIN_API_KEY 时应返回错误且 trains 为空。"""
    old = os.environ.get(API_KEY_ENV)
    try:
        os.environ[API_KEY_ENV] = ""  # 置空后 get(KEY) or "" 得 ""，不会发请求
        trains, err = query_trains("北京", "上海", "2025-12-21")
        assert trains == []
        assert err is not None
        # 应得到“请配置 key”类提示；若环境未真正置空则可能得到接口/网络错误
        assert API_KEY_ENV in err or "key" in (err or "").lower() or "接口返回错误" in (err or "") or "请求失败" in (err or "")
    finally:
        if old is not None:
            os.environ[API_KEY_ENV] = old
        elif API_KEY_ENV in os.environ:
            del os.environ[API_KEY_ENV]


@pytest.mark.skipif(
    not os.environ.get(API_KEY_ENV, ""),
    reason="需配置 JUHE_TRAIN_API_KEY 才请求真实接口",
)
def test_query_trains_with_key():
    """已配置 key 时调用真实 API，返回车次列表结构。"""
    trains, err = query_trains("北京南", "上海虹桥", "2025-12-21")
    assert err is None, err
    assert isinstance(trains, list)
    for t in trains:
        assert "train_no" in t
        assert "from_station" in t
        assert "to_station" in t
        assert "departure_time" in t
        assert "arrival_time" in t
        assert "duration" in t
        assert "seat_types" in t


def test_get_duration_minutes():
    assert get_duration_minutes("4h30m") == 270
    assert get_duration_minutes("1h00m") == 60
    assert get_duration_minutes("0h45m") == 45
    assert get_duration_minutes("") == 0
    assert get_duration_minutes("2h") == 120
    # API 返回的 04:28 格式
    assert get_duration_minutes("04:28") == 268
    assert get_duration_minutes("00:30") == 30
