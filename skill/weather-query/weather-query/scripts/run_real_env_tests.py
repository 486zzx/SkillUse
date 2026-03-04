#!/usr/bin/env python3
"""
天气查询 Skill 真实环境测试执行脚本。
遍历测试用例集，调用 run_weather_search.py，记录通过/失败与简要输出。
用法：在 weather-query 目录下执行 python scripts/run_real_env_tests.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
RUN_SCRIPT = SCRIPT_DIR / "run_weather_search.py"

# 测试用例全集：(用例ID, 描述, 命令行参数列表)
TEST_CASES = [
    # A. 基础查询
    ("TC-01", "仅地点-北京", ["北京"]),
    ("TC-02", "地点+今天", ["北京", "今天"]),
    ("TC-03", "地点+明天", ["上海", "明天"]),
    ("TC-04", "地点+后天", ["北京", "后天"]),
    ("TC-05", "地点+昨天", ["北京", "昨天"]),
    ("TC-06", "地点+具体日期", ["北京", "2026-03-10"]),
    ("TC-07", "地点+--days 5", ["北京", "--days", "5"]),
    ("TC-08", "中文城市-上海", ["上海"]),
    ("TC-09", "拼音地点-beijing", ["beijing"]),
    ("TC-10", "区级地点-北京朝阳区", ["北京朝阳区"]),
    # B. 可选参数
    ("TC-11", "生活指数--with-suggestion", ["北京", "--with-suggestion"]),
    ("TC-12", "空气质量--with-air", ["北京", "--with-air"]),
    ("TC-13", "生活指数+空气质量", ["北京", "--with-suggestion", "--with-air"]),
    ("TC-14", "天数--days 1", ["北京", "--days", "1"]),
    # C. 异常/边界
    ("TC-15", "无参数-应失败", []),
    ("TC-16", "经纬度地点", ["39.9:116.4"]),
]

# 成功用例的断言：需满足的条件
def _check_success(out: dict, tc_id: str) -> tuple[bool, str]:
    if not out.get("success"):
        return False, out.get("error", "unknown")
    r = out.get("result") or {}
    if not r.get("location") or not isinstance(r.get("location"), dict):
        return False, "missing or invalid result.location"
    if "current" not in r:
        return False, "missing result.current"
    if "daily" not in r or not isinstance(r["daily"], list):
        return False, "missing or invalid result.daily"
    if "TC-11" in tc_id or "TC-13" in tc_id:
        if "suggestion" not in r:
            return False, "missing result.suggestion (with-suggestion)"
    if "TC-12" in tc_id or "TC-13" in tc_id:
        if "air" not in r:
            return False, "missing result.air (with-air)"
    return True, ""

def _check_fail(out: dict) -> tuple[bool, str]:
    if out.get("success"):
        return False, "expected success=false"
    err = out.get("error", "")
    if "地点" in err or "参数" in err or "缺少" in err:
        return True, ""
    return True, err or "no error message"

def run_one(args: list[str]) -> tuple[int, str]:
    cmd = [sys.executable, str(RUN_SCRIPT)] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=str(SKILL_DIR),
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
        out_str = (result.stdout or "").strip()
        if result.returncode != 0 and not out_str and result.stderr:
            out_str = result.stderr.strip()
        return result.returncode, out_str
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as e:
        return -1, str(e)

def main() -> None:
    results = []
    for tc_id, desc, args in TEST_CASES:
        exit_code, out_str = run_one(args)
        try:
            out = json.loads(out_str) if out_str else {}
        except json.JSONDecodeError:
            out = {}
        if tc_id == "TC-15":
            ok, msg = _check_fail(out)
            status = "PASS" if ok else "FAIL"
            detail = msg or ("exit_code=%s" % exit_code)
        else:
            ok, msg = _check_success(out, tc_id)
            status = "PASS" if ok and exit_code == 0 else "FAIL"
            detail = msg if not ok else ("exit=%s" % exit_code)
        results.append({
            "id": tc_id,
            "desc": desc,
            "args": args,
            "status": status,
            "exit_code": exit_code,
            "detail": detail,
            "output_preview": out_str[:200] + "..." if len(out_str) > 200 else out_str,
        })
        print("%s %s %s" % (tc_id, status, desc))

    report = {
        "total": len(results),
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "failed": sum(1 for r in results if r["status"] == "FAIL"),
        "results": results,
    }
    out_path = SKILL_DIR / "references" / "real_env_test_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\nTotal: %d, Pass: %d, Fail: %d" % (report["total"], report["passed"], report["failed"]))
    print("Report written to: %s" % out_path)

if __name__ == "__main__":
    main()
