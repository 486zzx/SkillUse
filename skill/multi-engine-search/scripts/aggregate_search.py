#!/usr/bin/env python3
"""
聚合搜索入口：解析命令行 → 调用 aggregate → 打印 JSON。

用法:
  # 用户问题 + 多个 -k 传关键词（每个 -k 一条搜索词，关键词×引擎并行）
  python aggregate_search.py "python是什么" -k "python" -k "python 教程" -k "python 学习 26 教程"

  # 仅用户问题（不传 -k）：单 query 多引擎
  python aggregate_search.py "你的搜索关键词"

输出: 标准输出为 JSON（success, results, total_count, sources_used, query_rewrite.keywords, error）

耗时打桩: 设置环境变量 AGGREGATE_TIMING=1 时，各阶段耗时会打印到 stderr，便于定位慢点。
"""

from __future__ import annotations

import argparse
import json
import sys

# 入口脚本需从同目录加载模块
import aggregate


def main() -> int:
    parser = argparse.ArgumentParser(
        description="聚合搜索：第1参数=用户问题，用多个 -k 传关键词；关键词×引擎并行，去重排序后输出 JSON"
    )
    parser.add_argument("query", nargs="?", help="用户问题或搜索问句")
    parser.add_argument(
        "-k", "--keywords",
        action="append",
        default=None,
        metavar="KEYWORD",
        help="可多次使用，每条为一条搜索词，如 -k python -k \"python 教程\"",
    )
    parser.add_argument("--stdin", action="store_true", help="从标准输入读取一行作为 query")
    args = parser.parse_args()

    query = ""
    keywords: list[str] | None = None

    if args.stdin:
        query = sys.stdin.read().strip()
    else:
        query = (args.query or "").strip()
        if args.keywords:
            keywords = [x.strip() for x in args.keywords if x.strip()]

    if not query and not (keywords and len(keywords) > 0):
        print(json.dumps({
            "success": False,
            "results": [],
            "total_count": 0,
            "sources_used": [],
            "error": "未提供 query 或 -k 关键词：传用户问题，并用多个 -k 传关键词",
            "query_rewrite": None,
            "stats": {
                "total_original": 0,
                "total_after_dedup": 0,
                "dedup_rate": 0.0,
                "engine_counts": {},
                "duration_ms": 0,
            },
        }, ensure_ascii=False, indent=2))
        return 1

    out = aggregate.aggregate(query, keywords=keywords)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
