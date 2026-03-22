#!/usr/bin/env python3
"""
周边搜索 CLI：仅解析参数、输出 JSON。业务逻辑见 features.surround_service。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from client.http_client import RequestsHttpClient
from features.surround_service import normalize_surround_contract, surround_search
from skill_logging._log import silence_stdlib_root_logging

__all__ = ["surround_search", "normalize_surround_contract", "main"]

silence_stdlib_root_logging()


def ensure_cli_utf8_io() -> None:
    """Windows 控制台 UTF-8。"""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> None:
    ensure_cli_utf8_io()
    parser = argparse.ArgumentParser(description="周边搜索：地理编码 + 周边搜索")
    parser.add_argument("location", nargs="?", default="", help="目标地址，如 北京西站、三里屯")
    parser.add_argument("--city", default=None, help="城市名，如 北京")
    parser.add_argument("--keyword", default=None, help="搜索项（必选），如 餐厅、咖啡店")
    args = parser.parse_args()

    http_client = RequestsHttpClient()
    out_raw = asyncio.run(
        surround_search(args.location, args.keyword, args.city, http_client=http_client)
    )
    out = normalize_surround_contract(
        out_raw,
        address=args.location or "",
        keywords=args.keyword or "",
        city=args.city,
    )
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        out = normalize_surround_contract(
            {
                "success": False,
                "pois": [],
                "total_count": 0,
                "error": "运行异常：" + str(e),
            },
            address="",
            keywords="",
            city=None,
        )
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)
