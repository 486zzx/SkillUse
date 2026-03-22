#!/usr/bin/env python3
"""
处理 aggregate_calls.jsonl：
1. 筛选：有测试结果、搜索到内容、且没有 error 的项
2. 只保留 results 字段，且 results 中每条只保留 title、content、url、date
3. 输出为新的 jsonl 文件
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 结果条中只保留的字段（用户写的是 context，实际 API 为 content）
RESULT_FIELDS = ("title", "content", "url", "date")


def _keep_record(obj: dict) -> bool:
    """有测试结果、有搜索内容、且没有 error 的项才保留。"""
    out = obj.get("output") or {}
    if not out.get("success"):
        return False
    results = out.get("results") or []
    if not results:
        return False
    err = out.get("error") or ""
    if err and str(err).strip():
        return False
    return True


def _reduce_result(item: dict) -> dict:
    """单条 result 只保留 title、content、url、date。"""
    return {k: item.get(k) for k in RESULT_FIELDS}


def process(in_path: Path, out_path: Path) -> tuple[int, int]:
    """
    读取 in_path 的 jsonl，筛选后写入 out_path。
    返回 (总行数, 保留并写入的行数)。
    """
    total = 0
    kept = 0
    with open(in_path, "r", encoding="utf-8") as f_in, open(
        out_path, "w", encoding="utf-8"
    ) as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[WARN] skip line (invalid JSON): {e}", file=sys.stderr)
                continue
            if not _keep_record(obj):
                continue
            results = (obj.get("output") or {}).get("results") or []
            reduced = [_reduce_result(r) for r in results]
            f_out.write(json.dumps({"results": reduced}, ensure_ascii=False) + "\n")
            kept += 1
    return total, kept


def main() -> int:
    # 默认路径以脚本所在目录为基准，从任意 CWD 运行都能找到同目录下的 aggregate_calls.jsonl
    script_dir = Path(__file__).resolve().parent
    default_input = script_dir / "aggregate_calls.jsonl"

    parser = argparse.ArgumentParser(
        description="处理 aggregate_calls.jsonl：筛选有效且无 error 的项，只保留 results 中的 title/content/url/date，输出新 jsonl"
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=default_input,
        help="输入的 jsonl 路径（默认：与脚本同目录的 aggregate_calls.jsonl）",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="输出的 jsonl 路径（默认：与输入同目录的 aggregate_calls_filtered.jsonl）",
    )
    args = parser.parse_args()

    in_path = args.input
    if not in_path.is_file():
        print(f"[ERROR] 输入文件不存在: {in_path}", file=sys.stderr)
        return 1
    out_path = args.output if args.output is not None else (in_path.parent / "aggregate_calls_filtered.jsonl")

    total, kept = process(in_path, out_path)
    print(f"总行数: {total}, 保留并写入: {kept}, 输出: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
