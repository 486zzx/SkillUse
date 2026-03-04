"""
集成测试：使用代码中的「当前时间」构造用例，实际调用聚合 API，覆盖时间转化、API 调用、结果返回、排序等。
所有涉及日期的用例均以 datetime.now() 为基准，保证查询「之后」的车次，符合 API 限制。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from query_api import API_KEY_ENV

# 与 test_run_train_search 相同的运行方式
def _script_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts"


def _run(*args: str, timeout: int = 30) -> tuple[dict, int]:
    script = _script_dir() / "run_train_search.py"
    cmd = [sys.executable, str(script)] + list(args)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(_script_dir()),
        env=env,
    )
    out = (result.stdout or "").strip() or "{}"
    for line in reversed((out or "").splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            out = line
            break
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        data = {"error": (result.stderr or out) or "invalid output"}
    return data, result.returncode


def _today_tomorrow():
    """以代码中的当前时间为准，返回 (今天 yyyy-mm-dd, 明天 yyyy-mm-dd)。"""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    return today, tomorrow


@pytest.fixture(scope="module")
def ref_date():
    """模块级：当前时间基准，所有用例用同一基准避免跨天。"""
    return _today_tomorrow()


def _has_api_key() -> bool:
    return bool((os.environ.get(API_KEY_ENV) or "").strip())


def _require_key():
    if not _has_api_key():
        pytest.skip("需配置 JUHE_TRAIN_API_KEY 才执行 API 集成测试")


# ---------- 时间转化 ----------
def test_time_明天_解析为明天日期(ref_date):
    """时间转化：『明天』应被解析为代码中明天的日期。"""
    _require_key()
    today, tomorrow = ref_date
    data, code = _run("北京", "上海", "明天", timeout=30)
    assert code == 0, data.get("error")
    assert data.get("success") is True
    summary = data.get("query_summary") or {}
    dep_date = summary.get("departure_date", "")
    assert dep_date == tomorrow, f"预期 departure_date={tomorrow}，得到 {dep_date}（基准今天={today}）"


def test_time_今天_解析为今天日期(ref_date):
    """时间转化：『今天』应被解析为代码中今天的日期。"""
    _require_key()
    today, _ = ref_date
    data, code = _run("北京", "上海", "今天", timeout=30)
    assert code == 0, data.get("error")
    assert data.get("success") is True
    summary = data.get("query_summary") or {}
    assert (summary.get("departure_date") or "").startswith(today[:10]) or summary.get("departure_date") == today


def test_time_显式日期_原样使用(ref_date):
    """时间转化：显式 yyyy-mm-dd 应原样作为出发日期。"""
    _require_key()
    _, tomorrow = ref_date
    data, code = _run("北京", "上海", tomorrow, timeout=30)
    assert code == 0, data.get("error")
    assert data.get("success") is True
    assert (data.get("query_summary") or {}).get("departure_date") == tomorrow


# ---------- API 调用与结果返回 ----------
def test_api_调用成功且返回车次列表(ref_date):
    """API 调用：北京→上海、明天，应成功且 trains 非空。"""
    _require_key()
    data, code = _run("北京", "上海", "明天", timeout=30)
    assert code == 0
    assert data.get("success") is True
    assert "trains" in data and isinstance(data["trains"], list)
    assert data["total_count"] == len(data["trains"])
    assert data["total_count"] > 0, "应有至少一班车"


def test_api_结果结构_车次必含字段(ref_date):
    """结果返回：每条车次必须包含 train_no, from_station, to_station, departure_time, arrival_time, duration。"""
    _require_key()
    data, _ = _run("北京", "上海", "明天", "--max-results", "2", timeout=30)
    if not data.get("success") or not data.get("trains"):
        pytest.skip("API 未返回车次")
    required = ("train_no", "from_station", "to_station", "departure_time", "arrival_time", "duration")
    for t in data["trains"]:
        for k in required:
            assert k in t, f"车次缺少字段: {k}"


def test_api_结果结构_query_summary(ref_date):
    """结果返回：query_summary 应包含 from_station, to_station, departure_date。"""
    _require_key()
    data, _ = _run("北京", "上海", "明天", timeout=30)
    assert data.get("success") is True
    s = data.get("query_summary") or {}
    assert s.get("from_station") == "北京" and s.get("to_station") == "上海"
    assert len(s.get("departure_date", "")) >= 10


# ---------- 排序 ----------
def test_sort_price_asc(ref_date):
    """排序：--sort-by price_asc 时首条应为最低价。"""
    _require_key()
    data, _ = _run("北京", "上海", "明天", "--sort-by", "price_asc", "--max-results", "5", timeout=30)
    if not data.get("success") or len(data.get("trains", [])) < 2:
        pytest.skip("车次不足")
    trains = data["trains"]
    # 与脚本一致：按每趟车的最低票价排序，这里取每车最低价再断言升序
    prices = []
    for t in trains:
        per_train = []
        for s in (t.get("seat_types") or []):
            if isinstance(s, dict) and "price" in s and s["price"] is not None:
                try:
                    per_train.append(float(s["price"]))
                except (TypeError, ValueError):
                    pass
        if per_train:
            prices.append(min(per_train))
    if len(prices) < 2:
        pytest.skip("无法提取票价")
    assert prices == sorted(prices), "price_asc 应按价格升序"


def test_sort_departure_asc(ref_date):
    """排序：--sort-by departure_asc 时出发时间应升序。"""
    _require_key()
    data, _ = _run("北京", "上海", "明天", "--sort-by", "departure_asc", "--max-results", "5", timeout=30)
    if not data.get("success") or len(data.get("trains", [])) < 2:
        pytest.skip("车次不足")
    times = [t.get("departure_time", "") for t in data["trains"]]
    def to_m(t):
        if not t or ":" not in str(t):
            return 0
        p = str(t).strip().split(":")
        return int(p[0]) * 60 + (int(p[1]) if len(p) > 1 else 0)
    vals = [to_m(x) for x in times]
    assert vals == sorted(vals), "departure_asc 应按出发时间升序"


# ---------- 车型筛选 ----------
def test_train_type_G(ref_date):
    """车型筛选：--train-type G 时所有车次号应以 G 开头。"""
    _require_key()
    data, _ = _run("北京", "上海", "明天", "--train-type", "G", "--max-results", "5", timeout=30)
    if not data.get("success"):
        pytest.skip("API 未成功")
    for t in data.get("trains", []):
        assert (t.get("train_no") or "").upper().startswith("G"), f"应为 G 开头: {t.get('train_no')}"


# ---------- 数量限制 ----------
def test_max_results(ref_date):
    """结果返回：--max-results 3 时最多返回 3 条。"""
    _require_key()
    data, _ = _run("北京", "上海", "明天", "--max-results", "3", timeout=30)
    assert data.get("success") is True
    assert len(data["trains"]) <= 3
    assert data["total_count"] == len(data["trains"])


# ---------- 失败与边界 ----------
def test_缺少出发站_返回错误():
    """边界：缺少出发站时应 success=false 且 error 含提示。"""
    _, tomorrow = _today_tomorrow()
    data, code = _run("", "上海", tomorrow, timeout=15)
    assert data.get("success") is False
    assert "出发站" in (data.get("error") or "")


def test_缺少到达站_返回错误():
    """边界：缺少到达站时应 success=false。"""
    _, tomorrow = _today_tomorrow()
    data, code = _run("北京", "", tomorrow, timeout=15)
    assert data.get("success") is False
    assert "到达站" in (data.get("error") or "")
