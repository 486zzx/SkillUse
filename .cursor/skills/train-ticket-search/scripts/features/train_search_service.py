"""
列车班次查询业务逻辑（features）：可被 CLI 或代码直接 import。

- train_search(...)：函数入口
- _run_search(...)：内部执行查询（由 train_search 或 CLI 层调用）

命令行参数解析与 run_train_cli 仅在 scripts/run_train_search.py。
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Any

SERVICE_ERROR_MESSAGE = "服务异常，请稍后再试"

SCRIPT_DIR = Path(__file__).resolve().parent.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import config

DEFAULT_MAX_RESULTS = config.DEFAULT_MAX_RESULTS
PARSE_NATURAL_LANGUAGE_TIME = config.PARSE_NATURAL_LANGUAGE_TIME
TRAIN_TYPE_PREFIX = config.TRAIN_TYPE_PREFIX

from skill_logging._log import init_logger, log_event, trace_call

init_logger("train_search")
from features.filter_sort import (
    filter_by_arrival_time,
    filter_by_departure_time,
    sort_trains,
    SORT_OPTIONS,
    time_range_to_api_name,
)
from features.query_api import query_trains
from features.station_resolve import load_stations, resolve_station
from features.time_utils import (
    parse_arrival_time_array_or_string,
    parse_departure_time_array_or_string,
)

# 出发时间格式说明（用于报错/澄清文案，写清真实所需格式）
DEPARTURE_TIME_FORMAT_MSG = (
    '数组 ["yyyy-MM-dd HH:mm", "yyyy-MM-dd HH:mm"]（如 ["2026-03-18 00:00", "2026-03-18 23:59"]）'
    "或单日期 yyyy-MM-dd（如 2026-03-18）。"
)

# 参数英文 key → 中文名（用于报错时明确是哪个参数）
PARAM_NAME_CN = {
    "from_station": "出发站",
    "to_station": "到达站",
    "departure_time": "出发时间",
    "train_type": "车型",
}


def _format_missing_message(missing: list[str]) -> str:
    """根据缺失参数列表生成澄清文案，并注明出发时间的格式要求（若缺失）。"""
    names = [PARAM_NAME_CN.get(m, m) for m in missing]
    msg = "缺少必填参数：" + "、".join(names) + "。"
    if "departure_time" in missing:
        msg += "出发时间格式要求：" + DEPARTURE_TIME_FORMAT_MSG
    return msg


def _validate_params(dep_parsed: dict[str, str] | None, train_type_list: list[str] | None) -> dict[str, Any] | None:
    """
    校验出发日期与可选参数。不满足时返回用于澄清的 dict（clarification_needed + invalid + message），否则返回 None。
    - 出发日期须 ≥ 今日，否则接口报错。
    - train_type 仅允许 G/D/Z/T/K/O/F/S。
    """
    if not dep_parsed or not dep_parsed.get("date"):
        return None
    dep_date_str = (dep_parsed.get("date") or "").strip()[:10]
    if len(dep_date_str) != 10:
        return None
    try:
        dep_date = datetime.strptime(dep_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    today = date.today()
    if dep_date < today:
        return {
            "success": False,
            "trains": [],
            "total_count": 0,
            "clarification_needed": True,
            "invalid": ["departure_time"],
            "error": "参数「出发时间」不合法：仅支持查询今天及之后的列车，不能查询昨天及更早的日期。",
            "message": "参数「出发时间」不合法：出发日期须为今天或更晚，请修改后再查。",
        }
    if train_type_list:
        for t in train_type_list:
            c = (t or "").strip().upper()[:1]
            if c and c not in TRAIN_TYPE_PREFIX:
                return {
                    "success": False,
                    "trains": [],
                    "total_count": 0,
                    "clarification_needed": True,
                    "invalid": ["train_type"],
                    "error": f"参数「车型」不合法：传入值「{t}」无效，仅支持 G/D/Z/T/K/O/F/S。",
                    "message": "参数「车型」不合法：须为 G、D、Z、T、K、O、F、S 之一（可多选），请修正后重试。",
                }
    return None


def _trains_to_markdown(trains: list[dict[str, Any]]) -> str:
    """将车次列表转为 Markdown 表格字符串，节省 token。"""
    if not trains:
        return ""
    rows = []
    for t in trains:
        seat_parts = []
        for s in (t.get("seat_types") or []):
            if isinstance(s, dict):
                name = (s.get("name") or "").strip()
                price = s.get("price")
                if name:
                    seat_parts.append(f"{name}{price}" if price is not None else name)
        seat_str = " ".join(seat_parts) if seat_parts else "-"
        flags = t.get("train_flags") or []
        flag_str = " ".join(str(f).strip() for f in flags) if flags else "-"
        rows.append(
            "| {train_no} | {from_station} | {to_station} | {departure_time} | {arrival_time} | {duration} | {seat_str} | {flag_str} |".format(
                train_no=(t.get("train_no") or "").strip(),
                from_station=(t.get("from_station") or "").strip(),
                to_station=(t.get("to_station") or "").strip(),
                departure_time=(t.get("departure_time") or "").strip(),
                arrival_time=(t.get("arrival_time") or "").strip(),
                duration=(t.get("duration") or "").strip(),
                seat_str=seat_str,
                flag_str=flag_str,
            )
        )
    header = "| 车次 | 出发站 | 到达站 | 出发 | 到达 | 历时 | 座位票价 | 标签 |"
    sep = "|------|--------|--------|------|------|------|----------|------|"
    return "\n".join([header, sep] + rows)


@trace_call
async def _run_search(
    from_station: str,
    to_station: str,
    dep_parsed: dict[str, str],
    arr_parsed: dict[str, str] | None,
    train_filter: str | None,
    sort_by: str | None,
    raw_departure: str,
    raw_arrival: str | None,
    train_type_list: list[str] | None,
    *,
    http_client: Any,
) -> dict[str, Any]:
    """执行查询并返回结果字典（不退出进程）。trains 输出格式由 config.TRAINS_AS_MARKDOWN 控制。"""
    departure_date = dep_parsed["date"]
    dep_min = dep_parsed.get("time_min")
    dep_max = dep_parsed.get("time_max")
    api_range = time_range_to_api_name(dep_min, dep_max)
    arr_min = arr_parsed.get("time_min") if arr_parsed else None
    arr_max = arr_parsed.get("time_max") if arr_parsed else None

    trains, err = await query_trains(
        from_station,
        to_station,
        departure_date,
        train_filter=train_filter,
        departure_time_range=api_range,
        http_client=http_client,
    )
    if err:
        log_event(
            "_run_search",
            "query_trains_error",
            level="WARNING",
            detail=str(err),
            error=str(err),
        )
        return {
            "success": False,
            "trains": [],
            "total_count": 0,
            "error": SERVICE_ERROR_MESSAGE,
            "message": SERVICE_ERROR_MESSAGE,
            "clarification_needed": False,
        }

    trains = filter_by_departure_time(
        trains,
        range_name=api_range,
        time_min=dep_min,
        time_max=dep_max,
    )
    trains = filter_by_arrival_time(
        trains,
        range_name=None,
        time_min=arr_min,
        time_max=arr_max,
    )
    trains = sort_trains(trains, sort_by)

    if DEFAULT_MAX_RESULTS >= 0:
        trains = trains[:DEFAULT_MAX_RESULTS]

    query_summary = {
        "from_station": from_station,
        "to_station": to_station,
        "departure_date": departure_date,
        "departure_time": raw_departure,
        "departure_time_min": dep_min,
        "departure_time_max": dep_max,
        "arrival_time": raw_arrival,
        "arrival_time_min": arr_min,
        "arrival_time_max": arr_max,
        "train_type": train_type_list,
        "sort_by": sort_by,
    }
    log_event(
        "_run_search",
        "query_summary",
        level="INFO",
        output_summary={"query_summary": query_summary},
    )

    if config.TRAINS_AS_MARKDOWN:
        try:
            trains_out = _trains_to_markdown(trains)
        except Exception as e:
            log_event(
                "_run_search",
                "markdown_fallback",
                level="WARNING",
                detail=str(e),
                error=str(e),
            )
            trains_out = trains
    else:
        trains_out = trains

    out = {
        "success": True,
        "trains": trains_out,
        "total_count": len(trains),
        "error": "",
    }
    if len(trains) == 0:
        out["message"] = "该日期与线路上暂无符合条件的车次，可尝试调整出发日期、放宽筛选条件或更换站点。"
        out["reason"] = out["message"]
    return out


async def train_search(
    departure_station: str | None = None,
    arrival_station: str | None = None,
    departure_time: list[str] | str | None = None,
    arrival_time: list[str] | str | None = None,
    train_type: list[str] | str | None = None,
    sort_by: str | None = None,
    *,
    http_client: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    火车票/列车班次查询（函数调用入口）。

    参数：
        departure_station: 出发站或出发地（城市/站点名）
        arrival_station: 到达站或目的地（城市/站点名）
        departure_time: 出发时间。支持：
            - 数组 ["起始时间", "终止时间"]，如 ["2025-03-11 08:00", "2025-03-11 18:00"]
            - 数组 ["日期"] 表示该日全天，如 ["2025-03-11"]
            - 字符串 "yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm" 或单日期 "yyyy-MM-dd"
        arrival_time: 可选，到达时间。格式同 departure_time（数组或字符串）
        train_type: 可选，车型列表（["G","D"]）或逗号分隔字符串（如 "G,D"）。
        sort_by: 可选。出发时间 departure_asc / departure_desc；
                 到达时间 arrival_asc / arrival_desc；
                 耗时 duration_asc / duration_desc；
                 价格 price_asc / price_desc
    返回：
        与脚本输出一致的字典：success, trains, total_count, error 等。
        trains 为 Markdown 表格或车次数组由 config.TRAINS_AS_MARKDOWN 控制，命令行 --trains-format 可覆盖。
        参数问题返回 clarification_needed + missing/invalid；API/服务异常返回 error「服务异常，请稍后再试」（详情见日志）。
    """
    # 兼容旧参数名：from_station / to_station
    if (not departure_station) and kwargs.get("from_station"):
        departure_station = kwargs.get("from_station")
    if (not arrival_station) and kwargs.get("to_station"):
        arrival_station = kwargs.get("to_station")

    # 兼容 train_type 传字符串（如 "G,D"）
    train_type_list: list[str] | None
    if isinstance(train_type, str):
        train_type_list = [x.strip() for x in train_type.split(",") if x.strip()]
    else:
        train_type_list = train_type

    try:
        stations = load_stations()
    except Exception as e:
        log_event(
            "train_search",
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
    from_resolved = resolve_station((departure_station or "").strip(), stations) if stations else None
    to_resolved = resolve_station((arrival_station or "").strip(), stations) if stations else None
    if not from_resolved:
        return {
            "success": False,
            "trains": [],
            "total_count": 0,
            "clarification_needed": True,
            "missing": ["from_station"],
            "error": f"参数「出发站」无匹配：「{departure_station}」在站点表中未找到，请检查或更换表述。",
            "message": f"参数「出发站」无匹配：「{departure_station}」在站点表中未找到，请补全或修正。",
        }
    if not to_resolved:
        return {
            "success": False,
            "trains": [],
            "total_count": 0,
            "clarification_needed": True,
            "missing": ["to_station"],
            "error": f"参数「到达站」无匹配：「{arrival_station}」在站点表中未找到，请检查或更换表述。",
            "message": f"参数「到达站」无匹配：「{arrival_station}」在站点表中未找到，请补全或修正。",
        }
    from_name = from_resolved.get("station_name") or departure_station
    to_name = to_resolved.get("station_name") or arrival_station

    base = datetime.now()
    dep_parsed = parse_departure_time_array_or_string(
        departure_time,
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

    validation_err = _validate_params(dep_parsed, train_type_list)
    if validation_err:
        return validation_err

    arr_parsed = parse_arrival_time_array_or_string(
        arrival_time,
        time_base=base,
        allow_natural_language=PARSE_NATURAL_LANGUAGE_TIME,
    )

    raw_dep = departure_time if isinstance(departure_time, str) else json.dumps(departure_time, ensure_ascii=False)
    raw_arr = None
    if arrival_time is not None:
        raw_arr = arrival_time if isinstance(arrival_time, str) else json.dumps(arrival_time, ensure_ascii=False)

    train_filter = None
    if train_type_list:
        train_filter = ",".join((t or "").strip().upper()[:1] for t in train_type_list if (t or "").strip())

    if sort_by and sort_by not in SORT_OPTIONS:
        sort_by = None

    try:
        return await _run_search(
            from_name,
            to_name,
            dep_parsed,
            arr_parsed,
            train_filter,
            sort_by,
            raw_dep,
            raw_arr,
            train_type_list,
            http_client=http_client,
        )
    except Exception as e:
        log_event(
            "train_search",
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
