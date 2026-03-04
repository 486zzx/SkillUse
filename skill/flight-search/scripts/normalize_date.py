#!/usr/bin/env python3
"""
自然语言日期 → yyyy-mm-dd。
优先使用 jionlp.parse_time（若已安装），否则用 datetime 做简单相对日期（今天/明天/后天、N月M日）。
用法：
  python normalize_date.py "明天"
  python normalize_date.py "3月5号" --base 2026-03-01
  python normalize_date.py --json '["明天", "后天"]'
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


def _ensure_utf8_io() -> None:
    """避免 Windows 控制台 GBK 导致 print 报错或乱码，强制 stdout/stderr 使用 UTF-8。"""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _parse_with_jio(text: str, time_base: datetime) -> str | None:
    try:
        import jionlp as jio
    except ImportError:
        return None
    try:
        base_ts = time_base.timestamp()
        res = jio.parse_time(text, time_base=base_ts)
    except Exception:
        return None
    if not res or "time" not in res:
        return None
    t = res["time"]
    if isinstance(t, list) and len(t) >= 1:
        s = t[0]
        if isinstance(s, str) and len(s) >= 10:
            return s[:10]  # yyyy-mm-dd
    return None


def _parse_simple(text: str, base: datetime) -> str | None:
    """简单规则：今天/明天/后天、N月M日、yyyy-mm-dd。"""
    text = text.strip()
    if not text:
        return None

    # 今天 / 明天 / 后天
    for delta, kw in [(0, "今天"), (1, "明天"), (2, "后天")]:
        if kw in text or text == kw:
            d = base + timedelta(days=delta)
            return d.strftime("%Y-%m-%d")

    # 下周一 ~ 下周日（下周的星期X，Python weekday: 0=周一 … 6=周日）
    week_cn = ["一", "二", "三", "四", "五", "六", "日"]
    for wd, cn in enumerate(week_cn):
        if text == "下周" + cn or text == "下礼拜" + cn:
            days_ahead = (wd - base.weekday() + 7) % 7
            if days_ahead == 0:
                days_ahead = 7  # 今天就是该 weekday 时，取下星期
            d = base + timedelta(days=days_ahead)
            return d.strftime("%Y-%m-%d")

    # 已为 yyyy-mm-dd 或 yyyy/mm/dd
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = datetime(y, mo, d)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # N月M日 / N月M号
    m = re.search(r"(\d{1,2})月(\d{1,2})[日号]", text)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        y = base.year
        try:
            dt = datetime(y, mo, d)
            if dt < base:
                dt = datetime(y + 1, mo, d)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def normalize_date(text: str, time_base: datetime | None = None) -> dict:
    """
    解析单个日期字符串，返回 {"date": "yyyy-mm-dd", "source": "jio|simple|fail", "raw": "..."}
    """
    base = time_base or datetime.now()
    raw = text.strip()

    out = _parse_with_jio(raw, base)
    if out:
        return {"date": out, "source": "jio", "raw": raw}

    out = _parse_simple(raw, base)
    if out:
        return {"date": out, "source": "simple", "raw": raw}

    return {"date": "", "source": "fail", "raw": raw}


def main() -> None:
    _ensure_utf8_io()
    base = datetime.now()
    if "--base" in sys.argv:
        i = sys.argv.index("--base")
        try:
            base = datetime.fromisoformat(sys.argv[i + 1].replace("Z", "+00:00"))
        except (IndexError, ValueError):
            pass

    if "--json" in sys.argv:
        i = sys.argv.index("--json")
        try:
            texts = json.loads(sys.argv[i + 1])
        except (IndexError, json.JSONDecodeError):
            texts = []
    else:
        texts = [a.strip().strip('"') for a in sys.argv[1:] if not a.startswith("-") and a.strip()]
    if not texts:
        print(json.dumps({"error": "缺少输入：请用位置参数传入日期字符串，或 --json 传入 JSON 数组"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    results = [normalize_date(t, base) for t in texts]
    if len(results) == 1:
        print(json.dumps(results[0], ensure_ascii=False))
    else:
        print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
