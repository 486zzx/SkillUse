"""
航班查询业务逻辑（features）：地点→IATA、按出发时间范围查 API、可选筛选排序。

可被 CLI（run_flight_search.py）或其它代码直接 import：
  from features.flight_search import search_flights

命令行参数解析仅在 scripts/run_flight_search.py。
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import config

DATETIME_FMT = config.DATETIME_FMT
DEFAULT_MAX_SEGMENTS = config.DEFAULT_MAX_SEGMENTS
MAX_OUTPUT_FLIGHTS = config.MAX_OUTPUT_FLIGHTS

from skill_logging._log import init_logger, log_event, trace_call

# 直飞时从每条航班中移除的无用字段（segments、transferNum 等）
DIRECT_ONLY_STRIP_KEYS = ("segments", "transferNum")

# 标准日期时间格式正则（yyyy-MM-dd HH:mm）
_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}$")
# 从任意字符串中提取多段 yyyy-MM-dd HH:mm（不依赖 JSON/引号，兼容 PowerShell 等）
_DATETIME_FINDALL_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}")
# 从任意字符串中提取第一个日期（API 只接受 yyyy-MM-dd）
_DATE_ONLY_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
# 出发时间格式说明（用于报错/澄清文案）
DEPARTURE_TIME_FORMAT_MSG = (
    '数组为 ["yyyy-MM-dd HH:mm", "yyyy-MM-dd HH:mm"]（如 ["2026-03-21 00:00", "2026-03-21 23:59"]），'
    "或单日期 yyyy-MM-dd（如 2026-03-21）"
)

# 排序可选值：出发时间、到达时间、耗时、价格 的升序/降序
SORT_OPTIONS = (
    "departure_asc", "departure_desc",
    "arrival_asc", "arrival_desc",
    "duration_asc", "duration_desc",
    "price_asc", "price_desc",
)


def _parse_date_yyyy_mm_dd(s: str) -> date | None:
    """解析 yyyy-MM-dd 为 date，非法返回 None。"""
    if not s or len(s) < 10:
        return None
    s = s.strip()[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _is_standard_datetime(s: str) -> bool:
    s = (s or "").strip()
    if not s or len(s) < 16:
        return False
    return bool(_DATETIME_PATTERN.match(s[:16]))


def _is_strict_datetime_or_date(s: str) -> bool:
    """
    严格校验：必须为 10 位 yyyy-MM-dd 或 16 位 yyyy-MM-dd HH:mm，且为合法日期（时间）。
    拒绝如 2026-03-211、2026-02-30 等非法输入。
    """
    s = (s or "").strip()
    if not s:
        return False
    if len(s) == 10:
        try:
            datetime.strptime(s, "%Y-%m-%d")
            return True
        except ValueError:
            return False
    if len(s) == 16 and s[10] == " ":
        try:
            datetime.strptime(s, "%Y-%m-%d %H:%M")
            return True
        except ValueError:
            return False
    return False


def _normalize_time_range(value: list[str] | str | None) -> list[str]:
    """
    将时间参数规范为 [起始, 终止]，格式 yyyy-MM-dd HH:mm。
    - 若为 list 且长度为 2：取 [start, end] 并截取到 16 位。
    - 若为 list 且长度为 1：若该元素是 JSON 数组字符串则解析；否则按单值处理。
    - 若为 str：单日期 yyyy-MM-dd → 当日 00:00–23:59；单日期时间 → 该时刻到当日 23:59。
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        if len(value) >= 2:
            return [str(value[0]).strip()[:16], str(value[1]).strip()[:16]]
        if len(value) == 1:
            one = value[0]
            # 命令行传入的数组可能被解析成单元素字符串，如 '["2026-03-11 00:00","2026-03-11 23:59"]'
            # 或 PowerShell 去掉内层引号后 '[2026-03-11 00:00,2026-03-11 23:59]'
            if isinstance(one, str) and one.strip().startswith("["):
                one_norm = _normalize_json_like_string(one)
                try:
                    arr = json.loads(one_norm)
                    if isinstance(arr, list) and len(arr) >= 2:
                        return [str(arr[0]).strip()[:16], str(arr[1]).strip()[:16]]
                    if isinstance(arr, list) and len(arr) == 1:
                        value = arr[0]
                    else:
                        value = one
                except json.JSONDecodeError:
                    # 先尝试从整段中直接匹配两段 yyyy-MM-dd HH:mm（与火车 skill 一致，兼容 PowerShell）
                    found = _DATETIME_FINDALL_PATTERN.findall(one_norm)
                    if len(found) >= 2:
                        return [found[0].strip()[:16], found[1].strip()[:16]]
                    # 再尝试从整段中提取两个日期时间（兼容无引号、反斜杠等 shell 拆参）
                    inner = one_norm.strip()
                    if inner.startswith("["):
                        inner = inner[1:]
                    if inner.endswith("]"):
                        inner = inner[:-1]
                    inner = inner.replace("\\", "").strip()
                    if "," in inner:
                        parts = [p.strip().strip('"').strip()[:16] for p in inner.split(",", 1)]
                        if len(parts) == 2 and _DATETIME_PATTERN.match(parts[0]) and _DATETIME_PATTERN.match(parts[1]):
                            return parts
                    found = list(_DATE_ONLY_PATTERN.finditer(inner))
                    if len(found) >= 2:
                        m0, m1 = found[0], found[1]
                        end0 = m0.end()
                        if end0 < len(inner) and inner[end0] in "0123456789":
                            pass
                        else:
                            d1, d2 = m0.group(0), m1.group(0)
                            return [f"{d1} 00:00", f"{d2} 23:59"]
                    value = one
            else:
                value = one
        else:
            return []
    s = (value or "").strip()
    if not s:
        return []
    # 仅日期 yyyy-MM-dd（长度为 10）→ 当日 00:00–23:59
    if len(s) == 10 and re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return [f"{s} 00:00", f"{s} 23:59"]
    # 已有时间：从该时刻到当日 23:59
    if _DATETIME_PATTERN.match(s[:16]):
        return [s[:16], f"{s[:10]} 23:59"]
    return []


def _normalize_json_like_string(s: str) -> str:
    """规范化形如 JSON 的字符串：去 BOM、弯引号、PowerShell 可能传入的 \\\" 等，便于 json.loads。"""
    if not s:
        return s
    s = s.strip().lstrip("\ufeff")
    s = s.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    if '\\"' in s:
        s = s.replace('\\"', '"')
    return s


def _flights_to_markdown(flights: list[dict[str, Any]]) -> str:
    """将航班列表转为 Markdown 表格字符串，节省 token。出发/到达仅显示机场名（无三字码）；出发时间为当日时刻；到达时间为 +N 时刻（N 为相对出发日的天数）。"""
    if not flights:
        return ""
    rows = []
    for f in flights:
        dep_name = (f.get("departureName") or "").strip()
        dep_str = dep_name or (f.get("departure") or "").strip() or "-"
        arr_name = (f.get("arrivalName") or "").strip()
        arr_str = arr_name or (f.get("arrival") or "").strip() or "-"
        dep_date = (f.get("departureDate") or "").strip()
        dep_time = (f.get("departureTime") or "").strip()
        arr_date = (f.get("arrivalDate") or "").strip()
        arr_time = (f.get("arrivalTime") or "").strip()
        dep_ts = dep_time.strip() if dep_time else "-"
        # 到达：当日只显示时刻；跨日显示 +N 时刻（+0 不写）
        arr_day_offset = ""
        if dep_date and arr_date and len(dep_date) >= 10 and len(arr_date) >= 10:
            try:
                d0 = datetime.strptime(dep_date[:10], "%Y-%m-%d").date()
                d1 = datetime.strptime(arr_date[:10], "%Y-%m-%d").date()
                delta = (d1 - d0).days
                if delta == 0:
                    arr_day_offset = arr_time.strip() if arr_time else "-"
                else:
                    arr_day_offset = f"+{delta} {arr_time.strip()}" if arr_time else f"+{delta}"
            except ValueError:
                arr_day_offset = arr_time.strip() if arr_time else "-"
        else:
            arr_day_offset = arr_time.strip() if arr_time else "-"
        duration = (f.get("duration") or "").strip() or "-"
        price = f.get("ticketPrice")
        price_str = str(int(price)) if price is not None and price == price else "-"
        airline = (f.get("airlineName") or f.get("airline") or "").strip() or "-"
        flight_no = (f.get("flightNo") or "").strip() or "-"
        code_share = f.get("codeShareFlightNos") or []
        share_str = " ".join(str(x).strip() for x in code_share if x) if code_share else "-"
        rows.append(
            f"| {flight_no} | {airline} | {dep_str} | {dep_ts} | {arr_str} | {arr_day_offset} | {duration} | {price_str} | {share_str} |"
        )
    first_dep_date = (flights[0].get("departureDate") or "").strip()[:10]
    dep_col = f"出发时刻（{first_dep_date}当天）" if first_dep_date else "出发时刻"
    header = f"| 航班号 | 航司 | 出发 | {dep_col} | 到达 | 到达(+N=第N天后) | 耗时 | 票价 | 共享 |"
    sep = "|--------|------|------|----------------|------|------------------|------|------|------|"
    caption = f"以下航班均为 **{first_dep_date}** 出发。到达列当日仅显示时刻，+1 表示次日到达，+2 表示第3天，以此类推。\n\n" if first_dep_date else ""
    return caption + "\n".join([header, sep] + rows)


@trace_call
async def search_flights(
    origin: str,
    destination: str,
    departure_time: list[str] | str,
    arrival_time: list[str] | str | None = None,
    max_price: float | int | None = None,
    sort_by: str | None = None,
    *,
    http_client: Any,
) -> dict[str, Any]:
    """
    航班查询总入口（函数调用）。可直接在 Python 中调用，无需走命令行。
    直飞、输出格式等由 config.DIRECT_ONLY、config.FLIGHTS_AS_MARKDOWN 控制。
    http_client: 异步 HTTP 客户端实例（如 RequestsHttpClient），须由 CLI/run_* 或调用方每次创建并传入。

    参数：
      origin: 出发地（城市或机场名）
      destination: 目的地（城市或机场名）
      departure_time: 出发时间。可为 [起始, 终止]（yyyy-MM-dd HH:mm），或单个日期 "yyyy-MM-dd" / 日期时间 "yyyy-MM-dd HH:mm"（单日期视为当日 00:00–23:59）
      arrival_time: 可选。到达时间，格式同 departure_time
      max_price: 可选。只保留票价 ≤ 该值的航班
      sort_by: 可选。排序方式：departure_asc/desc、arrival_asc/desc、duration_asc/desc、price_asc/desc

    返回：
      成功：{"success": True, "flightInfo": "<markdown 表或 JSON 数组>", "flightCount": N}，无航班时带 message/reason；
      失败：{"success": False, "error": "..."}；
      参数不足：{"success": False, "clarification_needed": True, "missing": [...], "message": "..."}
    """
    init_logger("flight_search")
    hc = http_client
    # 规范化时间范围为 [start, end]（默认调用方已传入正确格式）
    dep_range = _normalize_time_range(departure_time)
    if not dep_range:
        return {
                "success": False,
                "clarification_needed": True,
                "missing": ["departure_time_range"],
                "message": f"请提供出发时间，{DEPARTURE_TIME_FORMAT_MSG}。",
                "error": "缺少出发时间范围",
            }
    if len(dep_range) >= 2 and (not _is_standard_datetime(dep_range[0]) or not _is_standard_datetime(dep_range[1])):
        return {
            "success": False,
            "clarification_needed": True,
            "missing": ["departure_time_range"],
            "message": f"出发时间须为合法日期时间，{DEPARTURE_TIME_FORMAT_MSG}。",
            "error": "出发时间格式无效",
        }

    arr_range: list[str] = []
    if arrival_time is not None:
        arr_range = _normalize_time_range(arrival_time)
        if len(arr_range) == 1:
            s = arr_range[0]
            if len(s) == 10 and re.match(r"^\d{4}-\d{2}-\d{2}$", s):
                arr_range = [f"{s} 00:00", f"{s} 23:59"]
            elif _is_standard_datetime(s):
                arr_range = [s[:16], f"{s[:10]} 23:59"]

    origin = (origin or "").strip()
    destination = (destination or "").strip()
    if not origin:
        return {
            "success": False,
            "clarification_needed": True,
            "missing": ["origin"],
            "message": "请提供出发地。",
            "error": "缺少出发地",
        }
    if not destination:
        return {
            "success": False,
            "clarification_needed": True,
            "missing": ["destination"],
            "message": "请提供目的地。",
            "error": "缺少目的地",
        }

    # 严格校验：起止时间必须为合法 yyyy-MM-dd（10 位）或 yyyy-MM-dd HH:mm（16 位），拒绝 2026-03-211、2026-02-30 等
    for i, seg in enumerate(dep_range):
        if not _is_strict_datetime_or_date(seg):
            return {
                "success": False,
                "clarification_needed": True,
                "invalid": ["departure_time_range"],
                "message": f"出发时间格式不合法，须为 {DEPARTURE_TIME_FORMAT_MSG}，且为合法日期（请勿使用如 2026-03-211、2026-02-30）。",
                "error": "出发时间格式不合法",
            }

    # API 只接受一个日期 yyyy-MM-dd：取第一段日期部分（已严格校验过）
    first_seg = dep_range[0].strip()
    departure_date = first_seg[:10] if len(first_seg) >= 10 else first_seg

    # 参数校验：出发日期不能早于今天（接口仅支持今天及之后）
    dep_date = _parse_date_yyyy_mm_dd(departure_date)
    if dep_date is None:
        return {
            "success": False,
            "clarification_needed": True,
            "missing": ["departure_time_range"],
            "message": f"出发日期格式无效，须为 yyyy-MM-dd（如 2026-03-21），或数组 {DEPARTURE_TIME_FORMAT_MSG}。",
            "error": "出发日期格式无效",
        }
    today = date.today()
    if dep_date < today:
        return {
            "success": False,
            "clarification_needed": True,
            "invalid": ["departure_time_range"],
            "message": "出发日期不能早于今天，仅支持查询今天及之后的航班，请修改出发日期。",
            "error": "出发日期不能早于今天",
        }

    # 参数校验：max_price 若传入则必须为正数
    if max_price is not None:
        try:
            p = float(max_price)
            if p <= 0 or (p != p):
                raise ValueError("must be positive")
        except (TypeError, ValueError):
            return {
                "success": False,
                "clarification_needed": True,
                "invalid": ["max_price"],
                "message": "价格上限 max_price 须为正数，请修改后重试。",
                "error": "max_price 参数无效",
            }

    # 参数校验：sort_by 若传入则必须在允许的排序选项中
    if sort_by is not None and (sort_by or "").strip():
        if (sort_by or "").strip().lower() not in SORT_OPTIONS:
            return {
                "success": False,
                "clarification_needed": True,
                "invalid": ["sort_by"],
                "message": "排序方式 sort_by 无效，可选：departure_asc/desc、arrival_asc/desc、duration_asc/desc、price_asc/desc。",
                "error": "sort_by 参数无效",
            }

    try:
        from features.location_to_iata import (
            get_data_dir,
            load_airport_map,
            load_maps,
            load_nearest_airport_map,
            resolve_iata,
        )
        from features.query_flight_api import query
        from features.filter_sort_flights import filter_and_sort
    except Exception as e:
        log_event(
            "search_flights",
            "module_load_failed",
            level="ERROR",
            error=str(e),
            detail=traceback.format_exc(),
        )
        return {"success": False, "error": "服务异常，请稍后再试", "message": "服务异常，请稍后再试"}

    data_dir = get_data_dir()
    if not (data_dir / "city_map.json").exists():
        log_event(
            "search_flights",
            "data_dir_invalid",
            level="ERROR",
            detail=str(data_dir),
        )
        return {"success": False, "error": "服务异常，请稍后再试", "message": "服务异常，请稍后再试"}

    city_map, province_map = load_maps(data_dir)
    airport_map = load_airport_map(data_dir) or None
    nearest_airport_map = load_nearest_airport_map(data_dir) or None

    o = resolve_iata(origin, city_map, province_map, airport_map, nearest_airport_map)
    d = resolve_iata(destination, city_map, province_map, airport_map, nearest_airport_map)

    if not o.get("iata"):
        return {
            "success": False,
            "clarification_needed": True,
            "invalid": ["origin"],
            "message": f"无法解析出发地「{origin}」，请检查输入或更换表述。",
            "error": "无法解析出发地",
        }
    if not d.get("iata"):
        return {
            "success": False,
            "clarification_needed": True,
            "invalid": ["destination"],
            "message": f"无法解析目的地「{destination}」，请检查输入或更换表述。",
            "error": "无法解析目的地",
        }

    dep, arr = o["iata"], d["iata"]
    resp = await query(
        departure=dep,
        arrival=arr,
        departure_date=departure_date,
        max_segments=DEFAULT_MAX_SEGMENTS,
        http_client=hc,
    )

    if resp.get("error_code") != 0:
        log_event("search_flights", "api_call_failed", level="ERROR", detail=str(resp))
        return {"success": False, "error": "服务异常，请稍后再试", "message": "服务异常，请稍后再试"}

    result = resp.get("result", {})
    info = result.get("flightInfo") or []

    filter_options: dict[str, Any] = {
        "departure_time_range": dep_range,
        "max_price": max_price,
        "sort_by": (sort_by or "").strip() or None,
    }
    if sort_by and sort_by.strip().lower() not in SORT_OPTIONS:
        filter_options["sort_by"] = None
    if arr_range and len(arr_range) >= 2 and _is_standard_datetime(arr_range[0]) and _is_standard_datetime(arr_range[1]):
        filter_options["arrival_time_range"] = arr_range
    if filter_options.get("max_price") is None:
        filter_options.pop("max_price", None)
    if filter_options.get("sort_by") is None:
        filter_options.pop("sort_by", None)

    info = filter_and_sort(info, filter_options)
    result["flightInfo"] = info
    result["flightCount"] = len(info)

    out_info = result.get("flightInfo") or []
    if MAX_OUTPUT_FLIGHTS >= 0 and len(out_info) > MAX_OUTPUT_FLIGHTS:
        result["flightInfo"] = out_info[:MAX_OUTPUT_FLIGHTS]
        result["flightCount"] = MAX_OUTPUT_FLIGHTS

    # orderid 仅写日志，不返回给调用方
    orderid = result.pop("orderid", None)
    if orderid is not None:
        log_event("search_flights", "orderid", level="INFO", output_summary={"orderid": orderid})

    flight_info = result.get("flightInfo") or []
    # 配置直飞时去掉 segments、transferNum 等无用字段
    if config.DIRECT_ONLY and flight_info:
        for f in flight_info:
            for k in DIRECT_ONLY_STRIP_KEYS:
                f.pop(k, None)
    flight_count = result.get("flightCount", 0)
    if config.FLIGHTS_AS_MARKDOWN:
        try:
            flight_info_out = _flights_to_markdown(flight_info)
        except Exception as e:
            log_event(
                "search_flights",
                "markdown_fallback",
                level="WARNING",
                detail=str(e),
                error=str(e),
            )
            flight_info_out = flight_info  # 返回未转换的原始 flightInfo 列表
    else:
        flight_info_out = flight_info
    out_payload: dict[str, Any] = {
        "success": True,
        "flightInfo": flight_info_out,
        "flightCount": flight_count,
    }
    if len(flight_info) == 0:
        out_payload["message"] = "该日期与航线上暂无符合条件的航班，可尝试调整出发日期、放宽筛选条件或更换航线。"
        out_payload["reason"] = out_payload["message"]
    return out_payload
