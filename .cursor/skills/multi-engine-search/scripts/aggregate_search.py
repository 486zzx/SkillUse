#!/usr/bin/env python3
"""
聚合搜索 CLI：解析参数、输出 JSON。业务逻辑见 features.aggregate。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Optional

from skill_logging._log import silence_stdlib_root_logging

# 不向 stdout/stderr 打印标准库 logging；结构化日志由 skill_logging/_log.py 写 JSONL
silence_stdlib_root_logging()

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import config
from client.http_client import RequestsHttpClient
from features import aggregate


def run_aggregate_from_cli(
    *,
    search_type_raw: str | None,
    search_mode_arg: str,
    keywords: list[str] | None,
    http_client: Optional[Any] = None,
) -> tuple[dict[str, Any], int]:
    """
    校验参数并执行聚合搜索。
    返回 (结果 dict, 进程退出码)。结果始终可 JSON 序列化。
    """
    search_mode_canonical = config.normalize_search_mode(search_mode_arg)
    if search_mode_canonical is None:
        return (
            {
                "success": False,
                "results": [],
                "total_count": 0,
                "error": f'无效的搜索模式 "{search_mode_arg}"，仅支持 Fast / Balanced / Precision（忽略大小写）',
            },
            1,
        )

    kw_list = [x.strip() for x in (keywords or []) if x and x.strip()]
    if not kw_list:
        return (
            {
                "success": False,
                "results": [],
                "total_count": 0,
                "error": "未提供关键词：请用多个 -k 传关键词",
            },
            1,
        )

    valid_categories = set(config.get_categories())
    default_category = (
        "知识问答"
        if "知识问答" in valid_categories
        else (list(valid_categories)[0] if valid_categories else "知识问答")
    )
    search_type_raw = (search_type_raw or default_category).strip()
    search_type_arg = [s.strip() for s in search_type_raw.split(",") if s.strip()] or [default_category]

    for st in search_type_arg:
        if st not in valid_categories:
            return (
                {
                    "success": False,
                    "results": [],
                    "total_count": 0,
                    "error": f'无效的搜索类型 "{st}"，必须为 16 类之一（直接写分类名）；当前有效分类：{sorted(valid_categories)}',
                },
                1,
            )

    hc = http_client or RequestsHttpClient()
    out = asyncio.run(
        aggregate.aggregate(
            keywords=kw_list,
            client=hc,
            search_type=search_type_arg if len(search_type_arg) != 1 else search_type_arg[0],
            search_mode=search_mode_canonical,
        )
    )
    exit_code = 0 if out.get("success") else 1
    return out, exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="聚合搜索：传搜索类型和关键词，按类型选引擎并发搜索，去重排序后输出 JSON"
    )
    parser.add_argument(
        "--search-type",
        default=None,
        metavar="TYPE",
        help="搜索类型：单分类或逗号分隔多分类（如 政策法规、知识问答、软件开发与IT），必须为 16 类之一；不传时默认 知识问答",
    )
    parser.add_argument(
        "--search-mode",
        default="Fast",
        metavar="MODE",
        help="搜索模式：Fast（默认）/ Balanced / Precision，忽略大小写；见 reference/search_modes.json",
    )
    parser.add_argument(
        "-k",
        "--keywords",
        action="append",
        default=None,
        metavar="KEYWORD",
        help='可多次使用，每条为一条搜索词，如 -k python -k "python 教程"',
    )
    args = parser.parse_args()

    out, code = run_aggregate_from_cli(
        search_type_raw=args.search_type,
        search_mode_arg=args.search_mode,
        keywords=args.keywords,
        http_client=None,
    )
    json_str = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.buffer.write(json_str.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
