#!/usr/bin/env python3
"""
run_weather_search 单次调用耗时分析。
测试例：北京 今天。逐项测量：进程启动、参数解析、日期解析(含 jionlp 首次 import)、
实况 API、逐日 API，输出各阶段耗时。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
RUN_SCRIPT = SCRIPT_DIR / "run_weather_search.py"


def run_with_timings() -> dict:
    """用 subprocess 跑一次完整命令，只得到总耗时。"""
    cmd = [sys.executable, str(RUN_SCRIPT), "北京", "今天"]
    t0 = time.perf_counter()
    result = subprocess.run(
        cmd,
        cwd=str(SKILL_DIR),
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    total_s = time.perf_counter() - t0
    return {"total_s": total_s, "exit_code": result.returncode, "stdout": result.stdout or "", "stderr": result.stderr or ""}


def run_in_process_timings() -> dict:
    """在同一进程内按 main 流程逐步执行并计时（不含进程启动）。"""
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))

    timings = {}
    t0 = time.perf_counter()

    # 1) 仅 import requests（脚本启动时的 import）
    import requests  # noqa: F401
    timings["import_requests_s"] = time.perf_counter() - t0

    # 2) 参数解析
    t1 = time.perf_counter()
    from run_weather_search import _parse_args, _get_auth_params  # noqa: E402
    auth = _get_auth_params()
    location, date_raw, days, with_suggestion, with_air, language, unit = _parse_args(["北京", "今天"])
    timings["parse_args_s"] = time.perf_counter() - t1

    # 3) 日期解析（会触发 jionlp 首次 import + parse_time）
    t2 = time.perf_counter()
    from run_weather_search import _date_to_start  # noqa: E402
    start = _date_to_start(date_raw)
    timings["date_to_start_s"] = time.perf_counter() - t2

    # 4) 实况 API
    t3 = time.perf_counter()
    from run_weather_search import _fetch_now  # noqa: E402
    loc_info, now_data = _fetch_now(location, auth, language, unit)
    timings["fetch_now_s"] = time.perf_counter() - t3

    # 5) 逐日 API
    t4 = time.perf_counter()
    from run_weather_search import _fetch_daily  # noqa: E402
    loc_daily, daily_list = _fetch_daily(location, auth, start, days, language, unit)
    timings["fetch_daily_s"] = time.perf_counter() - t4

    timings["in_process_total_s"] = time.perf_counter() - t0
    return timings


def main() -> None:
    print("=== 1) 子进程一次完整调用（含进程启动） ===\n")
    out = run_with_timings()
    print("总耗时: %.3f 秒" % out["total_s"])
    print("exit_code: %s" % out["exit_code"])
    if out["stderr"]:
        print("stderr 前 2 行:", (out["stderr"].strip().split("\n")[:2]))
    print()

    print("=== 2) 本进程内分阶段计时（不含进程启动） ===\n")
    timings = run_in_process_timings()
    for name, sec in timings.items():
        print("%s: %.3f 秒" % (name, sec))
    print()

    # 估算进程启动 + 脚本自身 import
    subprocess_total = out["total_s"]
    in_process_total = timings["in_process_total_s"]
    startup_approx = subprocess_total - in_process_total
    print("=== 3) 估算 ===\n")
    print("进程启动 + 脚本 import + 其它: 约 %.3f 秒" % startup_approx)
    print()

    # 汇总
    jio_related = timings.get("date_to_start_s", 0)
    api_total = timings.get("fetch_now_s", 0) + timings.get("fetch_daily_s", 0)
    print("=== 4) 耗时占比（本进程） ===\n")
    total = timings["in_process_total_s"]
    if total > 0:
        print("日期解析(含 jionlp): %.1f%%" % (100 * jio_related / total))
        print("心知 API(实况+逐日):  %.1f%%" % (100 * api_total / total))
        print("其它(参数/auth等):    %.1f%%" % (100 * (total - jio_related - api_total) / total))
    print()
    print("结论: 若 date_to_start_s 明显大于 1s，多为 jionlp 首次 import 与词典加载；")
    print("      fetch_now_s / fetch_daily_s 为两次 HTTP 往返，受网络与心知服务器影响。")


if __name__ == "__main__":
    main()
