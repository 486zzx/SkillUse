# -*- coding: utf-8 -*-
"""
天气查询 Skill 测试：入参为地点 + 时间范围（标准格式 yyyy-MM-dd,yyyy-MM-dd）。
- 3.1 地点输入（W-LOC）
- 3.2 日期/起始日（W-DAT，若可单测）
- 3.3 端到端（W-E2E）
- 3.4 输出处理（W-OUT）

API Key：SENIVERSE_KEY（或 SENIVERSE_UID + SENIVERSE_PRIVATE_KEY）。无 Key 时需 API 的用例跳过。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

SENIVERSE_KEY = os.environ.get("SENIVERSE_KEY", "").strip()
SKIP_E2E_WHEN_NO_KEY = True
requires_api_key = pytest.mark.skipif(
    SKIP_E2E_WHEN_NO_KEY and not SENIVERSE_KEY,
    reason="SENIVERSE_KEY 未配置，跳过需 API 的用例",
)

EVALS_DIR = Path(__file__).resolve().parent
SKILL_DIR = EVALS_DIR.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
RUN_WEATHER_SEARCH = SCRIPTS_DIR / "run_weather_search.py"


def _run_weather_search(*args, env=None):
    env = env or os.environ.copy()
    if SENIVERSE_KEY:
        env["SENIVERSE_KEY"] = SENIVERSE_KEY
    cmd = [sys.executable, str(RUN_WEATHER_SEARCH)] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(SKILL_DIR))
    out = (r.stdout or "").strip()
    try:
        return json.loads(out) if out else {"success": False, "error": r.stderr or "no output"}
    except json.JSONDecodeError:
        return {"success": False, "error": out or r.stderr}


# ---------------------------------------------------------------------------
# 3.1 地点输入（空为参数校验，可无 Key）
# ---------------------------------------------------------------------------
def test_W_LOC_05_empty():
    """空地点：应失败或参数校验失败。"""
    data = _run_weather_search("")
    assert data.get("success") is False or "error" in data or not data.get("result")


def _today_range(days: int = 1) -> str:
    """返回从今天起 days 天的标准格式时间范围。"""
    t = date.today()
    e = t + timedelta(days=days - 1)
    return f"{t.isoformat()},{e.isoformat()}" if days > 1 else t.isoformat()


def test_W_missing_time_range():
    """缺少时间范围时应报错。"""
    env = os.environ.copy()
    env["SENIVERSE_KEY"] = env.get("SENIVERSE_KEY") or "dummy"
    data = _run_weather_search("北京", env=env)
    assert data.get("success") is False
    assert "error" in data
    assert "时间范围" in (data.get("error") or "")


def test_W_location_chinese_only():
    """仅支持城市中文名：英文名应报错。"""
    env = os.environ.copy()
    env["SENIVERSE_KEY"] = env.get("SENIVERSE_KEY") or "dummy"
    data = _run_weather_search("beijing", _today_range(1), env=env)
    assert data.get("success") is False
    assert "error" in data
    err = data.get("error") or ""
    assert "中文" in err


# ---------------------------------------------------------------------------
# 3.3 端到端
# ---------------------------------------------------------------------------
@requires_api_key
def test_W_E2E_01_normal():
    """地点 + 时间范围（标准格式，3 天）。"""
    data = _run_weather_search("北京", _today_range(3))
    assert data.get("success") is True
    result = data.get("result") or {}
    assert "daily" in result
    assert "location" in result
    assert "time_range" in result
    assert len(result.get("daily") or []) <= 3


@requires_api_key
def test_W_E2E_02_days_max():
    """时间范围 6 天。"""
    data = _run_weather_search("上海", _today_range(6))
    assert data.get("success") is True
    result = data.get("result") or {}
    assert "daily" in result
    assert len(result.get("daily") or []) <= 6


@requires_api_key
def test_W_E2E_02b_weather_only():
    """仅查天气（不查空气）。"""
    data = _run_weather_search("北京", _today_range(2), "--query", "weather")
    assert data.get("success") is True
    result = data.get("result") or {}
    assert "daily" in result and len(result.get("daily") or []) <= 2
    assert result.get("air") == {}


@requires_api_key
def test_W_E2E_03_air():
    """仅查空气质量。"""
    data = _run_weather_search("北京", _today_range(1), "--query", "air")
    assert data.get("success") is True
    result = data.get("result") or {}
    assert "air" in result
    assert (result.get("daily") or []) == []  # 未选 weather


def test_W_E2E_04_no_key():
    """无 Key 时：应失败并提示配置。"""
    env = os.environ.copy()
    env.pop("SENIVERSE_KEY", None)
    env.pop("SENIVERSE_UID", None)
    env.pop("SENIVERSE_PRIVATE_KEY", None)
    data = _run_weather_search("北京", _today_range(1), env=env)
    assert "success" in data
    if not data.get("success"):
        assert "key" in (data.get("error") or "").lower() or "配置" in (data.get("error") or "")


# ---------------------------------------------------------------------------
# 3.4 输出处理
# ---------------------------------------------------------------------------
@requires_api_key
def test_W_OUT_02_single_day():
    """单日时间范围。"""
    data = _run_weather_search("北京", _today_range(1))
    assert data.get("success") is True
    daily = (data.get("result") or {}).get("daily") or []
    assert len(daily) <= 1


@requires_api_key
def test_W_OUT_08_combination():
    """时间范围 6 天 + 天气与空气质量。"""
    data = _run_weather_search("北京", _today_range(6), "--query", "both")
    assert data.get("success") is True
    result = data.get("result") or {}
    assert "air" in result
    assert "time_range" in result
    assert len(result.get("daily") or []) <= 6
