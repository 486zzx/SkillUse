# -*- coding: utf-8 -*-
"""
多引擎聚合搜索 Skill 测试：基于 docs/skill内部功能测试用例设计.md 第 5 节。
- 5.1 query 与 keywords 参数（M-QK）
- 5.2 输出处理与站点/域名限定（M-OUT）
- 5.2.1 重排序与 Pipeline（M-RER，单元）

API Key：TAVILY_API_KEY、BAIDU_APPBUILDER_API_KEY。无 Key 时需 API 的 E2E 跳过。
Pipeline 单元测试（M-RER-01～10）不需 Key。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "").strip()
BAIDU_APPBUILDER_API_KEY = os.environ.get("BAIDU_APPBUILDER_API_KEY", "").strip()
HAS_AGGREGATE_KEYS = bool(TAVILY_API_KEY and BAIDU_APPBUILDER_API_KEY)
SKIP_E2E_WHEN_NO_KEY = True
requires_api_key = pytest.mark.skipif(
    SKIP_E2E_WHEN_NO_KEY and not HAS_AGGREGATE_KEYS,
    reason="TAVILY_API_KEY 或 BAIDU_APPBUILDER_API_KEY 未配置，跳过需 API 的用例",
)

EVALS_DIR = Path(__file__).resolve().parent
SKILL_DIR = EVALS_DIR.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
AGGREGATE_SEARCH = SCRIPTS_DIR / "aggregate_search.py"


def _run_aggregate_search(*args, env=None):
    env = env or os.environ.copy()
    if TAVILY_API_KEY:
        env["TAVILY_API_KEY"] = TAVILY_API_KEY
    if BAIDU_APPBUILDER_API_KEY:
        env["BAIDU_APPBUILDER_API_KEY"] = BAIDU_APPBUILDER_API_KEY
    cmd = [sys.executable, str(AGGREGATE_SEARCH)] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(SKILL_DIR))
    out = (r.stdout or "").strip()
    try:
        return json.loads(out) if out else {"success": False, "error": r.stderr or "no output"}
    except json.JSONDecodeError:
        return {"success": False, "error": out or r.stderr}


# ---------------------------------------------------------------------------
# 5.1 keywords 参数（仅 -k，不再传用户原句）
# ---------------------------------------------------------------------------
def test_M_QK_03_no_keywords():
    """无 -k 无 --stdin：应报错。"""
    data = _run_aggregate_search()
    assert data.get("success") is False
    assert "error" in data
    assert "关键词" in (data.get("error") or "") or "k" in (data.get("error") or "").lower()


@requires_api_key
def test_M_QK_01_single_keyword():
    """仅传一个 -k。"""
    data = _run_aggregate_search("-k", "python是什么")
    assert data.get("success") is True
    assert "results" in data
    assert "sources_used" in data


@requires_api_key
def test_M_QK_02_multiple_keywords():
    """传多个 -k。"""
    data = _run_aggregate_search("-k", "Rust Go 性能", "-k", "Go 2024")
    assert data.get("success") is True
    assert "results" in data


# ---------------------------------------------------------------------------
# 5.2 输出处理
# ---------------------------------------------------------------------------
@requires_api_key
def test_M_OUT_03_max_items():
    data = _run_aggregate_search("-k", "python 教程")
    assert data.get("success") is True
    results = data.get("results") or []
    assert len(results) <= 50


@requires_api_key
def test_M_OUT_07_no_site():
    data = _run_aggregate_search("-k", "python 是什么")
    assert data.get("success") is True
    assert isinstance(data.get("results"), list)


# ---------------------------------------------------------------------------
# 5.2.1 重排序与 Pipeline（单元，不需 Key）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def pipeline_modules():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from dedupe import normalize_url, dedupe_by_url
    from pipeline import sort_by_relevance, run_pipeline
    return {"normalize_url": normalize_url, "dedupe_by_url": dedupe_by_url, "sort_by_relevance": sort_by_relevance, "run_pipeline": run_pipeline}


def test_M_RER_01_normalize_url(pipeline_modules):
    norm = pipeline_modules["normalize_url"]
    u = norm("https://a.com/p?utm_source=x&ref=y")
    assert "utm_source" not in u
    assert "a.com" in u or "/p" in u


def test_M_RER_03_dedupe_merge(pipeline_modules):
    dedupe = pipeline_modules["dedupe_by_url"]
    items = [
        {"url": "https://example.com/page", "title": "A", "content": "x", "source": "baidu"},
        {"url": "https://example.com/page?ref=1", "title": "A Longer", "content": "xy", "source": "tavily"},
    ]
    out = dedupe(items)
    assert len(out) == 1
    assert "sources" in out[0]
    assert len(out[0]["sources"]) == 2


def test_M_RER_05_sort_score_desc(pipeline_modules):
    sort_fn = pipeline_modules["sort_by_relevance"]
    items = [
        {"url": "https://a.com/1", "title": "Python tutorial", "content": "python guide"},
        {"url": "https://b.com/2", "title": "Other", "content": "other"},
    ]
    out = sort_fn(items, ["Python"])
    assert len(out) <= 2
    for o in out:
        assert "score" in o
    if len(out) >= 2:
        assert out[0]["score"] >= out[1]["score"]


def test_M_RER_08_spam_filter(pipeline_modules):
    sort_fn = pipeline_modules["sort_by_relevance"]
    items = [
        {"url": "https://spam.com", "title": "立即报名", "content": "免费试听"},
        {"url": "https://ok.com", "title": "Python", "content": "python"},
    ]
    out = sort_fn(items, ["Python"])
    urls = [o.get("url") or "" for o in out]
    assert "https://spam.com" not in urls or not out


def test_M_RER_10_run_pipeline(pipeline_modules):
    run = pipeline_modules["run_pipeline"]
    items = [
        {"url": "https://a.com/1", "title": "Python", "content": "python", "source": "baidu"},
        {"url": "https://a.com/1", "title": "Python", "content": "python", "source": "tavily"},
        {"url": "https://b.com/2", "title": "Go", "content": "go", "source": "baidu"},
    ]
    out = run(items, "Python", max_items=5)
    assert len(out) <= 5
    assert len(out) >= 1
