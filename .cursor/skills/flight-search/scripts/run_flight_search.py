#!/usr/bin/env python3
"""
航班查询 CLI：参数解析、UTF-8、输出 JSON。业务逻辑见 features.flight_search。

命令行：python run_flight_search.py 上海 北京 --departure-time '["2026-03-11 00:00","2026-03-11 23:59"]'
函数调用：from features.flight_search import search_flights
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from typing import Any

from client.http_client import RequestsHttpClient
from features.flight_search import config, search_flights
from skill_logging._log import silence_stdlib_root_logging

__all__ = ["search_flights", "parse_flight_cli_args", "config", "main"]

silence_stdlib_root_logging()


OPTION_KEYS = {
    "max-price": "max_price",
    "sort-by": "sort_by",
    "flights-format": "flights_format",
}

_DATETIME_FINDALL_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}")


def ensure_cli_utf8_io() -> None:
    """Windows 控制台 UTF-8。"""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _normalize_json_like_string(s: str) -> str:
    """规范化形如 JSON 的字符串：去 BOM、弯引号、PowerShell 可能传入的 \\\" 等。"""
    if not s:
        return s
    s = s.strip().lstrip("\ufeff")
    s = s.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    if '\\"' in s:
        s = s.replace('\\"', '"')
    return s


def _parse_departure_or_arrival_args(
    args: list[str], i: int, key: str
) -> tuple[list[str], int] | None:
    """解析 --departure-time 或 --arrival-time。"""
    if i + 1 >= len(args) or args[i + 1].startswith("--"):
        return None
    next_arg = args[i + 1].strip()
    if next_arg.startswith("["):
        combined = next_arg
        j = i + 2
        while not combined.strip().endswith("]") and j < len(args) and not args[j].startswith("--"):
            nxt = args[j].strip()
            if combined.rstrip().endswith('"') and nxt.startswith('"'):
                combined += "," + nxt
            else:
                combined += " " + nxt
            j += 1
        combined = _normalize_json_like_string(combined)
        try:
            arr = json.loads(combined)
            if isinstance(arr, list) and len(arr) >= 1:
                two = (
                    [str(arr[0]).strip()[:16], str(arr[1]).strip()[:16]]
                    if len(arr) >= 2
                    else [str(arr[0]).strip()[:16]]
                )
                return (two, j)
        except json.JSONDecodeError:
            pass
        found = _DATETIME_FINDALL_PATTERN.findall(combined)
        if len(found) >= 2:
            return ([found[0].strip()[:16], found[1].strip()[:16]], j)
        return ([combined], j)
    if i + 2 < len(args) and not args[i + 2].startswith("--"):
        return ([next_arg, args[i + 2].strip()], i + 3)
    return ([next_arg], i + 2)


def parse_flight_cli_args(argv: list[str]) -> tuple[str, str, list[str], list[str], dict[str, Any]]:
    """
    解析 argv：origin、destination、时间范围、options。
    返回 (origin, destination, departure_time_range, arrival_time_range, options)。
    """
    args = [a for a in argv if a != ""]
    positionals = []
    options: dict[str, Any] = {}
    departure_range: list[str] = []
    arrival_range: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:].strip().lower()
            if key == "departure-time":
                parsed = _parse_departure_or_arrival_args(args, i, key)
                if parsed:
                    departure_range, i = parsed
                    continue
            elif key == "arrival-time":
                parsed = _parse_departure_or_arrival_args(args, i, key)
                if parsed:
                    arrival_range, i = parsed
                    continue
            elif key == "direct":
                options["direct_only"] = True
                i += 1
                continue
            elif key in OPTION_KEYS and i + 1 < len(args) and not args[i + 1].startswith("--"):
                val = args[i + 1].strip()
                opt_key = OPTION_KEYS[key]
                if opt_key == "max_price":
                    try:
                        options[opt_key] = float(val)
                    except ValueError:
                        options[opt_key] = val
                else:
                    options[opt_key] = val
                i += 2
                continue
            i += 1
            continue
        positionals.append(a)
        i += 1
    origin = (positionals[0] or "").strip() if len(positionals) > 0 else ""
    destination = (positionals[1] or "").strip() if len(positionals) > 1 else ""
    return origin, destination, departure_range, arrival_range, options


def main() -> None:
    ensure_cli_utf8_io()
    origin, destination, departure_range, arrival_range, options = parse_flight_cli_args(
        sys.argv[1:]
    )

    if options.get("direct_only") is not None:
        config.DIRECT_ONLY = bool(options.get("direct_only"))
    if "flights_format" in options:
        config.FLIGHTS_AS_MARKDOWN = (
            options.get("flights_format", "markdown").strip().lower() != "json"
        )

    http_client = RequestsHttpClient()
    result = asyncio.run(
        search_flights(
            origin=origin,
            destination=destination,
            departure_time=departure_range,
            arrival_time=arrival_range if arrival_range else None,
            max_price=options.get("max_price"),
            sort_by=options.get("sort_by"),
            http_client=http_client,
        )
    )

    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
