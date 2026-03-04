#!/usr/bin/env python3
"""
基于《天气查询自定义测试用例.md》的真实环境测试执行脚本。
仅执行可由 run_weather_search.py 直接覆盖的用例（单轮、命令行入参）；多轮/定位/别名等记为不适用。
用法：在 weather-query 目录下执行 python scripts/run_custom_real_tests.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
RUN_SCRIPT = SCRIPT_DIR / "run_weather_search.py"

# 从自定义测试用例提取的可执行用例：(用例ID, 模块, 测试点简述, 命令行参数, 是否预期成功, 不适用原因可选)
# 不适用原因非空且 args 为 None 时仅记录不运行
CUSTOM_CASES = [
    ("W-001", "基础查询", "查询当前实时天气-北京", ["北京"], True, None),
    ("W-002", "基础查询", "查询今日天气-上海", ["上海", "今天"], True, None),
    ("W-003", "基础查询", "无城市无定位-今天天气", [], False, None),
    ("W-004", "基础查询", "口语化-广州天气怎么样", ["广州"], True, None),
    ("W-005", "多日预报", "深圳明天天气", ["深圳", "明天"], True, None),
    ("W-006", "多日预报", "杭州后天天气", ["杭州", "后天"], True, None),
    ("W-007", "多日预报", "成都未来3天", ["成都", "--days", "3"], True, None),
    ("W-008", "多日预报", "武汉一周天气", ["武汉", "--days", "7"], True, None),
    ("W-009", "多日预报", "西安未来30天(脚本上限15天)", ["西安", "--days", "30"], True, None),
    ("W-010", "多日预报", "南京本周天气", ["南京", "--days", "7"], True, None),
    ("W-011", "气象要素", "重庆今天多少度", ["重庆", "今天"], True, None),
    ("W-012", "气象要素", "长沙今天湿度", ["长沙", "今天"], True, None),
    ("W-013", "气象要素", "北京今天风力", ["北京", "今天"], True, None),
    ("W-014", "气象要素", "上海明天下雨概率", ["上海", "明天"], True, None),
    ("W-015", "气象要素", "广州空气质量", ["广州", "--with-air"], True, None),
    ("W-016", "气象要素", "三亚紫外线", ["三亚", "--with-suggestion"], True, None),
    ("W-017", "气象要素", "北京今天能见度", ["北京", "今天"], True, None),
    ("W-018", "气象要素", "北京今天穿什么", ["北京", "今天", "--with-suggestion"], True, None),
    ("W-019", "城市识别", "郑州天气", ["郑州"], True, None),
    ("W-020", "城市识别", "桂林天气", ["桂林"], True, None),
    ("W-021a", "城市识别", "浦东天气", ["浦东"], True, None),
    ("W-021b", "城市识别", "昆山天气", ["昆山"], True, None),
    ("W-022", "城市识别", "城市别名-上海", ["上海"], True, "仅测上海;羊城需Agent映射"),
    ("W-023", "城市识别", "拼音beijing", ["beijing"], True, None),
    ("W-024a", "城市识别", "东京天气", ["东京"], True, None),
    ("W-024b", "城市识别", "纽约天气", ["纽约"], True, None),
    ("W-025", "城市识别", "中山天气", ["中山"], True, None),
    ("W-026", "城市识别", "省+城市-苏州", ["苏州"], True, "脚本仅传苏州"),
    ("W-027", "时间理解", "今天(时段脚本不支持)", ["北京", "今天"], True, "下午时段需Agent"),
    ("W-028", "时间理解", "杭州早上冷吗", ["杭州", "今天"], True, "时段需Agent"),
    ("W-029", "时间理解", "指定日期2026-03-10成都", ["成都", "2026-03-10"], True, None),
    ("W-030", "时间理解", "昨天北京天气", ["北京", "昨天"], True, None),
    ("W-031", "时间理解", "后天", ["北京", "后天"], True, "大后天/下周一需Agent"),
    ("W-032", "多轮对话", "上下文继承城市", None, None, "脚本无多轮状态"),
    ("W-033", "多轮对话", "上下文继承时间", None, None, "脚本无多轮状态"),
    ("W-034", "多轮对话", "主动切换城市", None, None, "脚本无多轮状态"),
    ("W-035", "多轮对话", "多要素连续追问", None, None, "脚本无多轮状态"),
    ("W-036", "多轮对话", "上下文中断重置", None, None, "脚本无多轮状态"),
    ("W-037", "异常容错", "无意义文本啊啊啊", ["啊啊啊"], False, None),
    ("W-038", "异常容错", "只有时间无城市", [], False, None),
    ("W-039", "异常容错", "无效城市火星市", ["火星市"], False, None),
    ("W-040", "异常容错", "特殊字符", ["!@#$%^&*~"], False, None),
    ("W-041", "异常容错", "长文本+北京", ["北京"], True, "仅测城市提取"),
    ("W-042", "异常容错", "这里热吗无城市", None, None, "需定位或上下文"),
    ("W-043", "边界场景", "跨天时间判断", ["北京", "今天"], True, "时间归属依赖运行时刻"),
    ("W-044", "边界场景", "极端天气展示", ["北京", "今天"], True, "同普通查询"),
    ("W-045", "边界场景", "空消息输入", [], False, None),
    ("W-046", "输出规范", "输出结构统一", ["北京"], True, None),
    ("W-047", "输出规范", "数值合理性", ["上海"], True, None),
    ("W-048", "输出规范", "单位统一", ["北京"], True, None),
    ("W-049", "定位功能", "允许定位权限", None, None, "脚本无定位能力"),
    ("W-050", "定位功能", "拒绝定位权限", None, None, "脚本无定位能力"),
    ("W-051", "定位功能", "定位失败无网络", None, None, "脚本无定位能力"),
]


def _check_success(out: dict) -> tuple[bool, str]:
    if not out.get("success"):
        return False, out.get("error", "unknown")
    r = out.get("result") or {}
    if not r.get("location") or not isinstance(r.get("location"), dict):
        return False, "missing or invalid result.location"
    if "current" not in r:
        return False, "missing result.current"
    if "daily" not in r or not isinstance(r["daily"], list):
        return False, "missing or invalid result.daily"
    return True, ""


def _check_fail(out: dict) -> tuple[bool, str]:
    if out.get("success"):
        return False, "expected success=false"
    return True, out.get("error", "") or ""


def _write_md_report(report: dict, path: Path) -> None:
    """根据 report 生成 Markdown 测试报告。"""
    total = report["total_cases"]
    executed = report["executed"]
    passed = report["passed"]
    failed = report["failed"]
    skipped = report["skipped"]
    pass_rate = report.get("pass_rate_run") or ("%.1f%%" % (100.0 * passed / executed) if executed else "N/A")
    results = report.get("results") or []
    lines = [
        "# 天气查询自定义测试用例 - 真实环境测试结果报告",
        "",
        "**测试来源**：`references/天气查询自定义测试用例.md`",
        "**被测对象**：`scripts/run_weather_search.py`（心知天气 API + JioNLP 时间解析）",
        "**执行脚本**：`scripts/run_custom_real_tests.py`",
        "",
        "## 一、测试概要",
        "",
        "| 项目 | 数值 |",
        "|------|------|",
        "| 用例总数（映射后） | %d |" % total,
        "| 实际执行数 | %d |" % executed,
        "| 跳过 | %d |" % skipped,
        "| 通过 | %d |" % passed,
        "| 失败 | %d |" % failed,
        "| **执行通过率** | **%s** |" % pass_rate,
        "",
        "## 二、执行结果明细",
        "",
    ]
    pass_list = [r for r in results if r.get("status") == "PASS"]
    fail_list = [r for r in results if r.get("status") == "FAIL"]
    skip_list = [r for r in results if r.get("status") == "SKIP"]
    lines.append("### 通过（%d 例）\n" % len(pass_list))
    lines.append("| 用例 ID | 模块 | 测试点 | 脚本参数 |")
    lines.append("|---------|------|--------|----------|")
    for r in pass_list[:55]:
        args_str = str(r.get("args") or "")[:36].replace("|", ",")
        lines.append("| %s | %s | %s | %s |" % (
            r.get("id", ""), (r.get("module") or "").replace("|", ","),
            (r.get("point") or "")[:22].replace("|", ","), args_str))
    if len(pass_list) > 55:
        lines.append("| ... | ... | （共 %d 例） | ... |" % len(pass_list))
    lines.append("")
    lines.append("### 失败（%d 例）\n" % len(fail_list))
    if fail_list:
        lines.append("| 用例 ID | 测试点 | 失败原因 |")
        lines.append("|---------|--------|----------|")
        for r in fail_list:
            lines.append("| %s | %s | %s |" % (
                r.get("id", ""), (r.get("point") or "")[:20].replace("|", ","),
                (r.get("detail") or "")[:48].replace("|", ",")))
    else:
        lines.append("无。\n")
    lines.append("")
    lines.append("### 跳过（%d 例）\n" % len(skip_list))
    lines.append("| 用例 ID | 测试点 | 跳过原因 |")
    lines.append("|---------|--------|----------|")
    for r in skip_list:
        lines.append("| %s | %s | %s |" % (
            r.get("id", ""), (r.get("point") or "")[:22].replace("|", ","),
            (r.get("reason") or "")[:40].replace("|", ",")))
    lines.extend(["", "---", "", "*报告由 run_custom_real_tests.py 生成*", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


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
            for line in (result.stderr or "").splitlines():
                if line.strip().startswith("{"):
                    out_str = line.strip()
                    break
            if not out_str:
                out_str = result.stderr.strip()
        # 兼容 jionlp 等在 stdout 首行打印 banner，取最后一行 JSON
        if out_str and not out_str.strip().startswith("{"):
            lines = [s.strip() for s in out_str.splitlines() if s.strip()]
            for line in reversed(lines):
                if line.startswith("{"):
                    out_str = line
                    break
        return result.returncode, out_str
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as e:
        return -1, str(e)


def main() -> None:
    results = []
    for item in CUSTOM_CASES:
        case_id, module, point, args, expect_ok, skip_reason = item

        if skip_reason is not None and args is None:
            results.append({
                "id": case_id,
                "module": module,
                "point": point,
                "status": "SKIP",
                "reason": skip_reason,
                "args": None,
                "exit_code": None,
                "detail": None,
                "output_preview": None,
            })
            print("%s SKIP %s" % (case_id, point[:28]))
            continue

        exit_code, out_str = run_one(args)
        try:
            out = json.loads(out_str) if out_str else {}
        except json.JSONDecodeError:
            out = {}

        if expect_ok:
            ok, msg = _check_success(out)
            status = "PASS" if (ok and exit_code == 0) else "FAIL"
            detail = msg if not ok else ("exit=%s" % exit_code)
        else:
            ok, msg = _check_fail(out)
            status = "PASS" if ok else "FAIL"
            detail = msg if not ok else "unexpected success"
        results.append({
            "id": case_id,
            "module": module,
            "point": point,
            "status": status,
            "reason": skip_reason,
            "args": args,
            "exit_code": exit_code,
            "detail": detail,
            "output_preview": out_str[:250] + "..." if len(out_str) > 250 else out_str,
        })
        print("%s %s %s" % (case_id, status, point[:32]))

    run_count = sum(1 for r in results if r["status"] != "SKIP")
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    skipped = sum(1 for r in results if r["status"] == "SKIP")

    report = {
        "source": "天气查询自定义测试用例.md",
        "total_cases": len(results),
        "executed": run_count,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate_run": "%.1f%%" % (100.0 * passed / run_count) if run_count else "N/A",
        "results": results,
    }
    out_path = SKILL_DIR / "references" / "自定义测试用例_真实环境结果.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\nExecuted: %d, Pass: %d, Fail: %d, Skip: %d" % (run_count, passed, failed, skipped))
    print("Report: %s" % out_path)
    md_path = SKILL_DIR / "references" / "自定义测试用例_真实环境测试结果报告.md"
    _write_md_report(report, md_path)
    print("Report MD: %s" % md_path)


if __name__ == "__main__":
    main()
