#!/usr/bin/env python3
"""
运行 API 集成测试并生成测试报告。
使用方式：在 evals 目录下执行  python run_integration_report.py
或：python -m pytest test_api_integration.py -v --tb=short && python run_integration_report.py
报告输出到 evals/reports/api_integration_report.md
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 确保能导入 conftest 与测试
EVALS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = EVALS_DIR.parent
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR))

# 本进程也加载 .env，以便子进程 pytest 继承（conftest 会再加载一次，子进程内同样生效）
try:
    from dotenv import load_dotenv
    load_dotenv(SKILL_ROOT / ".env")
except ImportError:
    pass


def run_pytest() -> tuple[int, str]:
    """执行 test_api_integration.py，返回 (exitcode, stdout+stderr)。"""
    cmd = [
        sys.executable, "-m", "pytest",
        str(EVALS_DIR / "test_api_integration.py"),
        "-v", "--tb=short",
    ]
    env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
    # 多组真实 API 请求，总时长可能较长
    result = subprocess.run(
        cmd,
        cwd=str(EVALS_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=420,
        env=env,
    )
    out = (result.stdout or "") + "\n" + (result.stderr or "")
    return result.returncode, out


# 测试用例 ID 与可读名称映射（避免控制台编码导致报告乱码）
TEST_READABLE_NAMES = {
    "test_time_明天_解析为明天日期": "时间转化：明天 → 明天日期",
    "test_time_今天_解析为今天日期": "时间转化：今天 → 今天日期",
    "test_time_显式日期_原样使用": "时间转化：显式 yyyy-mm-dd 原样使用",
    "test_api_调用成功且返回车次列表": "API 调用成功且返回车次列表",
    "test_api_结果结构_车次必含字段": "结果结构：车次必含字段",
    "test_api_结果结构_query_summary": "结果结构：query_summary",
    "test_sort_price_asc": "排序：price_asc 价格升序",
    "test_sort_departure_asc": "排序：departure_asc 出发时间升序",
    "test_train_type_G": "车型筛选：仅 G",
    "test_max_results": "数量限制：max_results",
    "test_缺少出发站_返回错误": "边界：缺少出发站返回错误",
    "test_缺少到达站_返回错误": "边界：缺少到达站返回错误",
}


def _readable_name(nodeid_suffix: str) -> str:
    """从 test_xxx 得到可读名称。"""
    for k, v in TEST_READABLE_NAMES.items():
        if k in nodeid_suffix or nodeid_suffix in k:
            return v
    return nodeid_suffix


def parse_pytest_output(output: str) -> dict:
    """解析 pytest -v 输出，统计 passed/failed/skipped 及用例列表。"""
    lines = output.splitlines()
    passed, failed, skipped = [], [], []
    for line in lines:
        line_strip = line.strip()
        if "test_api_integration.py::" not in line_strip:
            continue
        # 提取 test_xxx 部分（可能含中文）
        rest = line_strip.split("test_api_integration.py::")[-1]
        name = rest.split(" PASSED")[0].split(" FAILED")[0].split(" SKIPPED")[0].strip()
        readable = _readable_name(name)
        if " PASSED" in line_strip:
            passed.append(readable)
        elif " FAILED" in line_strip:
            failed.append(readable)
        elif " SKIPPED" in line_strip:
            skipped.append(readable)
    summary = ""
    for line in lines:
        if "passed" in line and ("failed" in line or "skipped" in line or "error" in line):
            summary = line.strip()
            break
    return {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "summary": summary,
        "raw": output,
    }


def write_report(exitcode: int, parsed: dict, report_path: Path) -> None:
    """写入 Markdown 测试报告。"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    n_pass, n_fail, n_skip = len(parsed["passed"]), len(parsed["failed"]), len(parsed["skipped"])
    lines = [
        "# 火车票查询 API 集成测试报告",
        "",
        f"**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 1. 测试说明",
        "",
        "- 所有用例均以 **代码中的当前时间**（`datetime.now()`）为基准，查询「今天」「明天」或显式日期，保证请求为 API 允许的「之后」车次。",
        "- 覆盖：**时间转化**（明天/今天/显式日期）、**API 调用与结果结构**、**排序**（价格升序、出发时间升序）、**车型筛选**（G）、**数量限制**（max_results）、**边界**（缺站返回错误）。",
        "- 需配置环境变量 `JUHE_TRAIN_API_KEY`。若在 Cursor 中运行未拿到本机环境变量，可在 skill 根目录建 `.env` 写入 `JUHE_TRAIN_API_KEY=你的key`，脚本会通过 dotenv 自动加载。",
        "",
        "## 2. 结果汇总",
        "",
        f"- **通过**：{n_pass}",
        f"- **失败**：{n_fail}",
        f"- **跳过**：{n_skip}",
        f"- **汇总**：{parsed['summary']}",
        "",
        "## 3. 用例明细",
        "",
        "### 通过",
        "",
    ]
    for name in parsed["passed"]:
        lines.append(f"- `{name}`")
    lines.extend(["", "### 失败", ""])
    for name in parsed["failed"]:
        lines.append(f"- `{name}`")
    if not parsed["failed"]:
        lines.append("- 无")
    lines.extend(["", "### 跳过", ""])
    for name in parsed["skipped"]:
        lines.append(f"- `{name}`")
    if not parsed["skipped"]:
        lines.append("- 无")
    lines.extend([
        "",
        "## 4. 原始输出",
        "",
        "```",
        parsed["raw"][-8000:],  # 保留最后 8k 字符
        "```",
    ])
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    exitcode, output = run_pytest()
    parsed = parse_pytest_output(output)
    report_path = EVALS_DIR / "reports" / "api_integration_report.md"
    write_report(exitcode, parsed, report_path)
    print(f"报告已写入: {report_path}")
    return exitcode


if __name__ == "__main__":
    sys.exit(main())
