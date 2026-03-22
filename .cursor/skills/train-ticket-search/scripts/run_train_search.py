#!/usr/bin/env python3
"""
列车班次查询 CLI：参数解析、UTF-8、输出 JSON 均在本文件；业务逻辑见 features.train_search_service。
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import traceback
from datetime import datetime
from typing import Any

from client.http_client import RequestsHttpClient
from features.train_search_service import (
    DEPARTURE_TIME_FORMAT_MSG,
    PARAM_NAME_CN,
    PARSE_NATURAL_LANGUAGE_TIME,
    SERVICE_ERROR_MESSAGE,
    SORT_OPTIONS,
    _format_missing_message,
    _run_search,
    _validate_params,
    config,
    load_stations,
    parse_arrival_time_array_or_string,
    parse_departure_time_array_or_string,
    resolve_station,
    train_search,
)
from skill_logging._log import log_event, silence_stdlib_root_logging

__all__ = ["train_search", "main", "parse_train_cli_args", "run_train_cli"]


silence_stdlib_root_logging()


def ensure_cli_utf8_io() -> None:
    """避免 Windows 控制台 GBK 导致子进程输出解码失败。"""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# 命令行可选参数名（与航班一致风格）
OPTION_KEYS = {"train-type": "train_type", "sort-by": "sort_by", "trains-format": "trains_format"}

# 从任意字符串中提取两段 yyyy-MM-dd HH:mm（不依赖 JSON/引号，兼容 PowerShell 等）
_DATETIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}")


def _normalize_json_like_string(s: str) -> str:
    """规范化形如 JSON 的字符串：去 BOM、弯引号、PowerShell 可能传入的 \\\" 等，便于 json.loads。"""
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
    """解析 --departure-time 或 --arrival-time：支持数组 JSON、单值、或两个独立参数。返回 (range_list, next_i) 或 None。"""
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
                    [str(arr[0]).strip(), str(arr[1]).strip()]
                    if len(arr) >= 2
                    else [str(arr[0]).strip()]
                )
                return (two, j)
        except json.JSONDecodeError:
            pass
        found = _DATETIME_PATTERN.findall(combined)
        if len(found) >= 2:
            return ([found[0].strip(), found[1].strip()], j)
        return ([combined], j)
    if i + 2 < len(args) and not args[i + 2].startswith("--"):
        return ([next_arg, args[i + 2].strip()], i + 3)
    return ([next_arg], i + 2)


def parse_train_cli_args(argv: list[str]) -> tuple[str, str, list[str], list[str], dict]:
    """
    解析 argv（与航班一致）：
    - 前两个非 flag 为 from_station, to_station；
    - --departure-time / --arrival-time；
    - --train-type（可多次）、--sort-by 等进入 options。
    返回 (from_station, to_station, departure_range, arrival_range, options)。
    """
    args = [a for a in argv if a != ""]
    positionals = []
    options = {}
    departure_range: list[str] = []
    arrival_range: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:].strip().lower().replace("_", "-")
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
            elif key == "train-type" and i + 1 < len(args) and not args[i + 1].startswith("--"):
                options.setdefault("train_type", []).append(args[i + 1].strip())
                i += 2
                continue
            elif key in OPTION_KEYS and i + 1 < len(args) and not args[i + 1].startswith("--"):
                options[OPTION_KEYS[key]] = args[i + 1].strip()
                i += 2
                continue
            i += 1
            continue
        positionals.append(a)
        i += 1
    from_station = (positionals[0] or "").strip() if len(positionals) > 0 else ""
    to_station = (positionals[1] or "").strip() if len(positionals) > 1 else ""
    return from_station, to_station, departure_range, arrival_range, options


def _cli_time_to_input(
    dep_range: list[str], arr_range: list[str]
) -> tuple[list[str] | str | None, list[str] | str | None]:
    """将 parse_train_cli_args 得到的时间范围转为 parse_*_time_array_or_string 的输入。"""
    dep_in = (
        dep_range[:2]
        if len(dep_range) >= 2
        else (dep_range[0] if len(dep_range) == 1 and dep_range[0] else None)
    )
    arr_in = None
    if arr_range:
        arr_in = (
            arr_range[:2]
            if len(arr_range) >= 2
            else (arr_range[0] if len(arr_range) == 1 and arr_range[0] else None)
        )
    return dep_in, arr_in


def _ensure_time_is_list_or_str(value: list[str] | str | None) -> list[str] | str | None:
    """若为形如 JSON 数组的字符串，则解析为 list。兼容 PowerShell 等传入的整段字符串。"""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    s = (value or "").strip()
    if not s or len(s) < 2 or not s.startswith("[") or not s.endswith("]"):
        return value
    s = _normalize_json_like_string(s)
    try:
        arr = json.loads(s)
        if isinstance(arr, list) and len(arr) >= 1:
            return [str(x).strip() for x in arr[:2]]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    m = re.match(r"\[\s*[\"']([^\"']*)[\"']\s*,\s*[\"']([^\"']*)[\"']\s*\]", s)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]
    found = _DATETIME_PATTERN.findall(s)
    if len(found) >= 2:
        return [found[0].strip(), found[1].strip()]
    if len(found) == 1 and re.search(r"\d{4}-\d{2}-\d{2}", s):
        date_part = re.search(r"\d{4}-\d{2}-\d{2}", s).group(0)
        return [found[0].strip(), f"{date_part} 23:59"]
    return value


async def run_train_cli(
    argv: list[str], *, http_client: Any | None = None
) -> dict[str, Any]:
    """解析 CLI 参数并执行查询，返回结果 dict（不打印、不 sys.exit）。"""
    hc = http_client if http_client is not None else RequestsHttpClient()
    from_station, to_station, dep_range, arr_range, options = parse_train_cli_args(argv)
    dep_input, arr_input = _cli_time_to_input(dep_range, arr_range)
    dep_input = _ensure_time_is_list_or_str(dep_input)
    arr_input = _ensure_time_is_list_or_str(arr_input)

    missing = []
    if not from_station:
        missing.append("from_station")
    if not to_station:
        missing.append("to_station")
    if dep_input is None or (
        isinstance(dep_input, str) and not dep_input.strip()
    ) or (isinstance(dep_input, list) and len(dep_input) == 0):
        missing.append("departure_time")
    if missing:
        names = [PARAM_NAME_CN.get(m, m) for m in missing]
        return {
            "success": False,
            "trains": [],
            "total_count": 0,
            "clarification_needed": True,
            "missing": missing,
            "error": "缺少必填参数：" + "、".join(names) + "。",
            "message": _format_missing_message(missing),
        }

    try:
        stations = load_stations()
    except Exception as e:
        log_event(
            "run_train_cli",
            "load_stations_failed",
            level="ERROR",
            error=str(e),
            detail=traceback.format_exc(),
        )
        return {
            "success": False,
            "trains": [],
            "total_count": 0,
            "error": SERVICE_ERROR_MESSAGE,
            "message": SERVICE_ERROR_MESSAGE,
            "clarification_needed": False,
        }

    from_resolved = resolve_station(from_station, stations) if stations else None
    to_resolved = resolve_station(to_station, stations) if stations else None
    if not from_resolved:
        return {
            "success": False,
            "trains": [],
            "total_count": 0,
            "clarification_needed": True,
            "missing": ["from_station"],
            "error": f"参数「出发站」无匹配：「{from_station}」在站点表中未找到，请检查或更换表述。",
            "message": f"参数「出发站」无匹配：「{from_station}」在站点表中未找到，请补全或修正。",
        }
    if not to_resolved:
        return {
            "success": False,
            "trains": [],
            "total_count": 0,
            "clarification_needed": True,
            "missing": ["to_station"],
            "error": f"参数「到达站」无匹配：「{to_station}」在站点表中未找到，请检查或更换表述。",
            "message": f"参数「到达站」无匹配：「{to_station}」在站点表中未找到，请补全或修正。",
        }
    from_name = from_resolved.get("station_name") or from_station
    to_name = to_resolved.get("station_name") or to_station

    base = datetime.now()
    dep_parsed = parse_departure_time_array_or_string(
        dep_input,
        time_base=base,
        allow_natural_language=PARSE_NATURAL_LANGUAGE_TIME,
    )
    if not dep_parsed or not dep_parsed.get("date"):
        return {
            "success": False,
            "trains": [],
            "total_count": 0,
            "clarification_needed": True,
            "missing": ["departure_time"],
            "error": "参数「出发时间」格式不正确，须为：" + DEPARTURE_TIME_FORMAT_MSG,
            "message": "参数「出发时间」格式不正确或缺失，须为：" + DEPARTURE_TIME_FORMAT_MSG,
        }

    train_type_list = options.get("train_type") or []
    validation_err = _validate_params(dep_parsed, train_type_list)
    if validation_err:
        return validation_err

    arr_parsed = None
    if arr_input is not None:
        arr_parsed = parse_arrival_time_array_or_string(
            arr_input,
            time_base=base,
            allow_natural_language=PARSE_NATURAL_LANGUAGE_TIME,
        )
    train_filter = (
        ",".join((t or "").strip().upper()[:1] for t in train_type_list if (t or "").strip())
        if train_type_list
        else None
    )
    sort_by = options.get("sort_by")
    if sort_by and sort_by not in SORT_OPTIONS:
        sort_by = None
    raw_departure = (
        json.dumps(dep_input, ensure_ascii=False)
        if isinstance(dep_input, list)
        else (dep_input or "")
    )
    raw_arrival = (
        json.dumps(arr_input, ensure_ascii=False)
        if isinstance(arr_input, list)
        else (arr_input or None)
        if arr_input
        else None
    )

    if "trains_format" in options:
        config.TRAINS_AS_MARKDOWN = options.get("trains_format") != "json"
    try:
        result = await _run_search(
            from_name,
            to_name,
            dep_parsed,
            arr_parsed,
            train_filter,
            sort_by,
            raw_departure,
            raw_arrival,
            train_type_list or None,
            http_client=hc,
        )
    except Exception as e:
        log_event(
            "run_train_cli",
            "run_search_failed",
            level="ERROR",
            error=str(e),
            detail=traceback.format_exc(),
        )
        return {
            "success": False,
            "trains": [],
            "total_count": 0,
            "error": SERVICE_ERROR_MESSAGE,
            "message": SERVICE_ERROR_MESSAGE,
            "clarification_needed": False,
        }
    return result


async def main() -> None:
    ensure_cli_utf8_io()
    result = await run_train_cli(sys.argv[1:])
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    asyncio.run(main())
