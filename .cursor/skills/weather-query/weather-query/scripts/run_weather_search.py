#!/usr/bin/env python3
"""
天气查询 CLI：参数解析、UTF-8、输出 JSON。业务逻辑见 features.weather_service。
"""
from __future__ import annotations

import asyncio
import json
import sys

from client.http_client import RequestsHttpClient
from features.weather_service import (
    DEFAULT_LANGUAGE,
    DEFAULT_UNIT,
    parse_query_type_from_str,
    run_weather_search,
)
from skill_logging._log import silence_stdlib_root_logging

__all__ = ["run_weather_search", "parse_weather_cli_args", "main"]

silence_stdlib_root_logging()


def ensure_cli_utf8_io() -> None:
    """Windows 控制台 UTF-8。"""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_weather_cli_args(
    argv: list[str],
) -> tuple[str, str, set[str], str, str]:
    """解析 argv：地点、时间范围字符串（标准格式）、query（weather/air/both）、language、unit。"""
    args = [a for a in argv if a != ""]
    positionals = []
    query_type = {"weather"}
    language = DEFAULT_LANGUAGE
    unit = DEFAULT_UNIT
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:].strip().lower()
            if key == "query" and i + 1 < len(args) and not args[i + 1].startswith("--"):
                query_type = parse_query_type_from_str(args[i + 1])
                i += 1
            elif key == "language" and i + 1 < len(args) and not args[i + 1].startswith("--"):
                language = (args[i + 1] or "").strip() or language
                i += 1
            elif key == "unit" and i + 1 < len(args) and not args[i + 1].startswith("--"):
                unit = (args[i + 1] or "").strip() or unit
                i += 1
            i += 1
            continue
        positionals.append(a)
        i += 1
    location = (positionals[0] or "").strip() if positionals else ""
    time_range_raw = (positionals[1] or "").strip() if len(positionals) > 1 else ""
    return location, time_range_raw, query_type, language, unit


def main() -> None:
    ensure_cli_utf8_io()
    if len(sys.argv) < 2:
        err = {
            "success": False,
            "error": "缺少参数：需要至少地点与时间范围（标准格式），例如：run_weather_search.py 北京 2026-03-10,2026-03-12",
            "message": "缺少参数：需要至少地点与时间范围（标准格式），例如：run_weather_search.py 北京 2026-03-10,2026-03-12",
        }
        print(json.dumps(err, ensure_ascii=False, separators=(",", ":")))
        sys.exit(1)

    location, time_range_raw, query_type, language, unit = parse_weather_cli_args(
        sys.argv[1:]
    )
    http_client = RequestsHttpClient()
    result = asyncio.run(
        run_weather_search(
            location,
            time_range_raw,
            http_client=http_client,
            query=query_type,
            language=language,
            unit=unit,
        )
    )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
