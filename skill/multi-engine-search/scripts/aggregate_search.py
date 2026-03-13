#!/usr/bin/env python3
"""
聚合搜索入口：解析命令行 → 调用 aggregate → 打印 JSON。

用法:
  # 多个 -k 传关键词 + 指定搜索类型（16 个分类型之一或 general/code/news）
  python aggregate_search.py --search-type 政策法规 -k "劳动法" -k "试用期"
  python aggregate_search.py --search-type code -k "python" -k "python 教程"

  # 从标准输入读取关键词（每行一个）
  echo -e "python\npython 教程" | python aggregate_search.py --stdin

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
        description="聚合搜索：传搜索类型和关键词，按类型选引擎并发搜索，去重排序后输出 JSON"
    )
    parser.add_argument(
        "--search-type",
        default="general",
        metavar="TYPE",
        help="搜索类型：单分类或逗号分隔多分类（如 政策法规 或 政策法规,知识问答），多分类时按进阶版权重合并；默认 general",
    )
    parser.add_argument(
        "--search-mode",
        choices=["快速", "思考", "专家"],
        default="快速",
        metavar="MODE",
        help="搜索模式：快速 / 思考 / 专家，默认 快速（暂仅透传，后续可拓展）",
    )
    parser.add_argument(
        "-k", "--keywords",
        action="append",
        default=None,
        metavar="KEYWORD",
        help="可多次使用，每条为一条搜索词，如 -k python -k \"python 教程\"",
    )
    parser.add_argument("--stdin", action="store_true", help="从标准输入读取关键词，每行一个")
    args = parser.parse_args()

    keywords: list[str] | None = None
    if args.stdin:
        raw = sys.stdin.read().strip()
        keywords = [line.strip() for line in raw.splitlines() if line.strip()]
    elif args.keywords:
        keywords = [x.strip() for x in args.keywords if x.strip()]

    if not keywords or len(keywords) == 0:
        print(json.dumps({
            "success": False,
            "results": [],
            "total_count": 0,
            "sources_used": [],
            "error": "未提供关键词：请用多个 -k 传关键词，或 --stdin 传入（每行一个）",
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

    # 支持逗号分隔多分类，单参数时仍为单元素列表
    search_type_raw = (args.search_type or "general").strip()
    search_type_arg = [s.strip() for s in search_type_raw.split(",") if s.strip()] or ["general"]

    out = aggregate.aggregate(
        keywords=keywords,
        search_type=search_type_arg if len(search_type_arg) != 1 else search_type_arg[0],
        search_mode=args.search_mode,
    )
    json_str = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.buffer.write(json_str.encode('utf-8'))
    sys.stdout.buffer.write(b'\n')  # 加个换行符，保持格式整洁
    return 0 if out.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
