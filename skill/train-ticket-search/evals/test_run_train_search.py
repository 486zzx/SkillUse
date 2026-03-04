"""run_train_search 主入口集成测试（通过子进程调用脚本，会实际请求聚合 API）。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from query_api import API_KEY_ENV


def _script_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts"


def _run(*args: str, timeout: int = 30) -> tuple[dict, int]:
    """执行 run_train_search.py，返回 (解析后的 stdout JSON, returncode)。"""
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
    # jionlp 等库 import 时可能向 stdout 打印 banner，取最后一行作为 JSON
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


def test_run_success():
    """有 API Key 时成功返回车次；无 Key 时返回配置错误（脚本仍输出 JSON，可能 exit 1）。"""
    data, code = _run("北京", "上海", "2025-12-21")
    assert code in (0, 1)
    assert "trains" in data
    if data.get("success"):
        assert code == 0
        assert data.get("total_count") == len(data["trains"])
        if data["trains"]:
            t = data["trains"][0]
            assert "train_no" in t and "from_station" in t and "to_station" in t
    else:
        assert data.get("total_count") == 0
        err = (data.get("error") or "").lower()
        # 无 key 时为配置提示；有 key 时可能是接口错误、日期限制或网络超时
        assert (
            API_KEY_ENV.lower() in err
            or "key" in err
            or "接口返回错误" in (data.get("error") or "")
            or "日期" in (data.get("error") or "")
            or "请求失败" in (data.get("error") or "")
            or "timeout" in err
            or "timed out" in err
        )


def test_run_with_sort():
    data, code = _run("北京", "上海", "2025-12-21", "--sort-by", "price_asc")
    assert code in (0, 1)
    assert "trains" in data
    if data.get("success") and data["trains"]:
        assert data.get("query_summary", {}).get("sort_by") == "price_asc"


def test_run_with_train_type():
    data, code = _run("北京", "上海", "2025-12-21", "--train-type", "G", timeout=30)
    assert code in (0, 1)
    if data.get("success"):
        for t in data.get("trains", []):
            assert t.get("train_no", "").upper().startswith("G")


def test_run_missing_from():
    data, code = _run("", "上海", "2025-12-21")
    assert code != 0 or data.get("success") is False
    assert "出发站" in (data.get("error") or "")


def test_run_natural_language_date():
    """自然语言日期（如明天）应由主入口内部转为 yyyy-mm-dd。"""
    data, code = _run("杭州", "南京", "明天")
    assert code in (0, 1)
    assert "query_summary" in data or data.get("error")
    if data.get("success"):
        summary = data.get("query_summary") or {}
        dep = summary.get("departure_date", "")
        assert len(dep) >= 10 and dep[4] == "-" and dep[7] == "-", f"departure_date 应为 yyyy-mm-dd，得到 {dep!r}"


def test_run_output_structure():
    """成功时输出必须包含 success, trains, total_count, query_summary；trains 每项含 train_no/from_station/to_station 等。"""
    data, _ = _run("北京", "上海", "2025-12-21")
    assert "success" in data and "trains" in data and "total_count" in data
    assert data["total_count"] == len(data["trains"])
    if data.get("success") and data.get("trains"):
        t = data["trains"][0]
        for key in ("train_no", "from_station", "to_station", "departure_time", "arrival_time", "duration"):
            assert key in t, f"车次对象应包含 {key}"
    if data.get("success"):
        summary = data.get("query_summary") or {}
        assert "from_station" in summary and "to_station" in summary and "departure_date" in summary


def test_run_failure_structure():
    """失败时应有 success=false、error 非空、trains 为空。"""
    data, code = _run("", "上海", "2025-12-21")
    assert data.get("success") is False
    assert "error" in data and (data.get("error") or "").strip()
    assert data.get("trains") == [] and data.get("total_count") == 0


def test_run_with_max_results():
    """--max-results 应限制返回条数。"""
    data, _ = _run("北京", "上海", "2025-12-21", "--max-results", "3")
    if data.get("success") and data.get("trains"):
        assert len(data["trains"]) <= 3
        assert data["total_count"] == len(data["trains"])


@pytest.mark.skipif(
    not (os.environ.get(API_KEY_ENV) or "").strip(),
    reason="需配置 JUHE_TRAIN_API_KEY 才执行真实接口测试",
)
def test_run_real_api_success():
    """有 key 时：北京到上海、明天，应成功且返回车次列表（实际调用聚合 API）。"""
    data, code = _run("北京", "上海", "明天", timeout=30)
    assert code == 0, f"脚本应正常退出，得到: {data.get('error', '')}"
    assert data.get("success") is True, f"预期 success=true，得到: {data.get('error', '')}"
    assert "trains" in data and isinstance(data["trains"], list)
    assert data["total_count"] == len(data["trains"])
    assert data["total_count"] > 0, "应有至少一班车"
    t = data["trains"][0]
    for key in ("train_no", "from_station", "to_station", "departure_time", "arrival_time", "duration"):
        assert key in t, f"车次对象缺少字段: {key}"
    summary = data.get("query_summary") or {}
    assert summary.get("from_station") == "北京" and summary.get("to_station") == "上海"
    assert len(summary.get("departure_date", "")) >= 10
