#!/usr/bin/env python3
"""
基于 JioNLP 时间解析测试例的天气查询日期用例测试。
参考：https://github.com/dongrixinyu/JioNLP/blob/master/test/test_time_parser.py
用例为模糊时间字符串，调用 run_weather_search.py 北京 <date_raw>，校验返回的逐日预报首日
与 _date_to_start 解析结果一致。
用法：在 weather-query 目录下执行 python scripts/run_jionlp_date_tests.py
可选：python scripts/run_jionlp_date_tests.py --quick 10  仅跑前 10 条以快速出报告
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
RUN_SCRIPT = SCRIPT_DIR / "run_weather_search.py"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# 从 JioNLP test_time_parser.py 选取的模糊时间用例（单日或取首日）
# 格式: (用例ID, 描述, 用户输入的时间字符串)
JIONLP_DATE_CASES = [
    # 限定日：今天/明天/后天/昨天/前天
    ("JIO-01", "今天", "今天"),
    ("JIO-02", "明天", "明天"),
    ("JIO-03", "后天", "后天"),
    ("JIO-04", "昨天", "昨天"),
    ("JIO-05", "前天", "前天"),
    ("JIO-06", "大后天上午10点", "大后天上午10点"),
    ("JIO-07", "大大后天", "大大后天"),
    ("JIO-08", "本日", "本日"),
    ("JIO-09", "today", "today"),
    ("JIO-10", "tomorrow", "tomorrow"),
    ("JIO-11", "yesterday", "yesterday"),
    # 星期
    ("JIO-12", "下周六", "下周六"),
    ("JIO-13", "下周周六", "下周周六"),
    ("JIO-14", "下个星期一", "下个星期一"),
    ("JIO-15", "星期天", "星期天"),
    ("JIO-16", "上周六中午12点", "上周六中午12点"),
    ("JIO-17", "上个礼拜天", "上个礼拜天"),
    # 月日
    ("JIO-18", "9月30日", "9月30日"),
    ("JIO-19", "本月9日", "本月9日"),
    ("JIO-20", "下月九号", "下月九号"),
    ("JIO-21", "上个月15号", "上个月15号"),
    ("JIO-22", "3月8号", "3月8号"),
    ("JIO-23", "6·30", "6·30"),
    ("JIO-24", "09-01", "09-01"),
    ("JIO-25", "1月3", "1月3"),
    ("JIO-26", "十月31", "十月31"),
    ("JIO-27", "十二月20号", "十二月20号"),
    # 标准数字日期
    ("JIO-28", "2019/04/19", "2019/04/19"),
    ("JIO-29", "2019.9.6", "2019.9.6"),
    ("JIO-30", "20240307", "20240307"),
    ("JIO-31", "2022 11 23", "2022 11 23"),
    ("JIO-32", "2015年8月12日", "2015年8月12日"),
    ("JIO-33", "15年3月2日", "15年3月2日"),
    ("JIO-34", "2026-03-10", "2026-03-10"),
    # 带时分（取日）
    ("JIO-35", "明天下午3点", "明天下午3点"),
    ("JIO-36", "明天下午3点至下午8点", "明天下午3点至下午8点"),
    ("JIO-37", "昨晚8时35分", "昨晚8时35分"),
    ("JIO-38", "今天十一点半", "今天十一点半"),
    ("JIO-39", "翌日", "翌日"),
    # 时间范围（脚本取首日）
    ("JIO-40", "前天中午到明天晚上", "前天中午到明天晚上"),
    ("JIO-41", "今天下午1点到3点十分", "今天下午1点到3点十分"),
    # 相对+月
    ("JIO-42", "明年3月份", "明年3月份"),
    ("JIO-43", "去年3月3号", "去年3月3号"),
]


def _start_to_first_daily_date(start: int | str, today: date) -> str:
    """将 _date_to_start 的返回值转为心知 daily 首日 yyyy-mm-dd。"""
    if isinstance(start, int):
        d = today + timedelta(days=start)
        return d.strftime("%Y-%m-%d")
    # "yyyy/m/d"
    parts = str(start).split("/")
    if len(parts) != 3:
        return ""
    try:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        return date(y, m, d).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return ""


def _run_script(date_raw: str) -> tuple[int, str]:
    """执行 run_weather_search.py 北京 <date_raw>，返回 (exit_code, stdout 末行)。"""
    cmd = [sys.executable, str(RUN_SCRIPT), "北京", date_raw]
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
        out = (result.stdout or "").strip()
        # 兼容 jionlp 等库在 stderr 打印 banner，stdout 可能多行，取最后一行 JSON
        lines = [s.strip() for s in out.splitlines() if s.strip()]
        last = lines[-1] if lines else out
        return result.returncode, last
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as e:
        return -1, str(e)


def _get_first_daily_date_from_output(out_str: str) -> tuple[bool, str, str]:
    """
    从脚本输出解析 JSON，取 result.daily[0].date。
    返回 (success, first_date_yyyy_mm_dd, error_message)。
    """
    try:
        data = json.loads(out_str)
    except json.JSONDecodeError:
        return False, "", "JSON 解析失败"
    if not data.get("success"):
        return False, "", data.get("error", "success=false")
    result = data.get("result") or {}
    daily = result.get("daily") or []
    if not daily:
        return False, "", "result.daily 为空"
    first = daily[0]
    if not isinstance(first, dict):
        return False, "", "daily[0] 非对象"
    first_date = first.get("date") or ""
    if not first_date or len(first_date) < 10:
        return False, "", "daily[0].date 缺失或无效"
    return True, first_date[:10], ""


def run_jionlp_date_tests(cases: list | None = None) -> dict:
    """执行 JioNLP 日期用例，返回报告字典。cases 默认 JIONLP_DATE_CASES。"""
    import run_weather_search as rws  # noqa: PLC0415

    if cases is None:
        cases = JIONLP_DATE_CASES
    _date_to_start = rws._date_to_start
    today = date.today()
    results = []
    for tc_id, desc, date_raw in cases:
        exit_code, out_str = _run_script(date_raw)
        ok_out, actual_first_date, err_msg = _get_first_daily_date_from_output(out_str)
        start = _date_to_start(date_raw)
        expected_first = _start_to_first_daily_date(start, today)
        date_ok = expected_first and actual_first_date == expected_first
        if ok_out and exit_code == 0 and date_ok:
            status = "PASS"
            detail = "首日=%s" % actual_first_date
        elif not ok_out or exit_code != 0:
            status = "FAIL"
            detail = err_msg or "exit=%s" % exit_code
        else:
            status = "FAIL"
            detail = "首日期望=%s 实际=%s" % (expected_first, actual_first_date)
        results.append({
            "id": tc_id,
            "desc": desc,
            "date_raw": date_raw,
            "status": status,
            "exit_code": exit_code,
            "expected_first_date": expected_first,
            "actual_first_date": actual_first_date if ok_out else "",
            "detail": detail,
        })
    report = {
        "total": len(results),
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "failed": sum(1 for r in results if r["status"] == "FAIL"),
        "source": "JioNLP test_time_parser 模糊时间用例",
        "results": results,
    }
    return report


def main() -> None:
    quick = 0
    if "--quick" in sys.argv:
        i = sys.argv.index("--quick")
        if i + 1 < len(sys.argv):
            try:
                quick = max(1, int(sys.argv[i + 1]))
            except ValueError:
                pass
    cases = JIONLP_DATE_CASES[:quick] if quick else JIONLP_DATE_CASES
    report = run_jionlp_date_tests(cases)
    for r in report["results"]:
        print("%s %s %s | %s" % (r["id"], r["status"], r["desc"], r["detail"]))
    print("\nTotal: %d, Pass: %d, Fail: %d" % (
        report["total"], report["passed"], report["failed"]))
    out_json = SKILL_DIR / "references" / "jionlp_date_test_report.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("Report JSON: %s" % out_json)
    out_md = SKILL_DIR / "references" / "jionlp_date_test_report.md"
    _write_md_report(report, out_md)
    print("Report Markdown: %s" % out_md)


def _write_md_report(report: dict, path: Path) -> None:
    """生成 Markdown 测试报告。"""
    total = report["total"]
    passed = report["passed"]
    pct = 100.0 * passed / total if total else 0
    lines = [
        "# 天气查询 · JioNLP 模糊时间用例测试报告",
        "",
        "基于 [JioNLP test_time_parser](https://github.com/dongrixinyu/JioNLP/blob/master/test/test_time_parser.py) 中的模糊时间测试例，"
        "构造天气查询命令 `run_weather_search.py 北京 <date_raw>`，校验逐日预报首日与脚本内 `_date_to_start`（JioNLP）解析结果一致。",
        "",
        "## 汇总",
        "",
        "| 项目 | 数量 |",
        "|------|------|",
        "| 总用例数 | %d |" % total,
        "| 通过 | %d |" % passed,
        "| 失败 | %d |" % report["failed"],
        "| 通过率 | %.1f%% |" % pct,
        "",
        "## 用例结果",
        "",
        "| 用例ID | 描述 | 用户时间输入 | 期望首日 | 实际首日 | 状态 | 说明 |",
        "|--------|------|--------------|----------|----------|------|------|",
    ]
    for r in report["results"]:
        desc_esc = (r["desc"] or "").replace("|", "\\|")
        raw_esc = (r["date_raw"] or "")[:20].replace("|", "\\|")
        detail_esc = (r.get("detail") or "")[:30].replace("|", "\\|")
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["id"],
            desc_esc,
            raw_esc,
            r.get("expected_first_date") or "-",
            r.get("actual_first_date") or "-",
            r["status"],
            detail_esc,
        ))
    lines.extend(["", "---", "*报告由 scripts/run_jionlp_date_tests.py 生成*", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
