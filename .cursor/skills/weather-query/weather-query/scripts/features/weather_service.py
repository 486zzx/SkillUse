"""
天气查询业务逻辑（features）：可被 CLI 或代码直接 import。

  from features.weather_service import run_weather_search

命令行参数解析仅在 scripts/run_weather_search.py。
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from skill_logging._log import init_logger, trace_call
from features.api_request import fetch_daily, fetch_air
import config

AIR_VALID_DAYS = config.AIR_VALID_DAYS
DEFAULT_LANGUAGE = config.DEFAULT_LANGUAGE
DEFAULT_UNIT = config.DEFAULT_UNIT
SENIVERSE_KEY_DEFAULT = config.SENIVERSE_KEY_DEFAULT
WEATHER_MAX_DAYS = config.WEATHER_MAX_DAYS
WEATHER_WINDOW_END_DAYS = config.WEATHER_WINDOW_END_DAYS
WEATHER_WINDOW_START_OFFSET = config.WEATHER_WINDOW_START_OFFSET


def _error_out(error: str, message: str | None = None) -> dict[str, Any]:
    """统一 weather-query 失败结构：补齐 message 字段。"""
    return {
        "success": False,
        "error": error or "",
        "message": (message if message is not None else (error or "")),
    }

# 标准日期格式 yyyy-MM-dd
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 地点仅支持城市中文名：至少包含一个中文字符，拒绝纯英文/数字/经纬度/ID
_LOCATION_ZH = re.compile(r"[\u4e00-\u9fff]")
_LOCATION_LOOKS_LIKE_COORDS = re.compile(r"^\s*\d+\.?\d*\s*:\s*\d+\.?\d*\s*$")
_LOCATION_LOOKS_LIKE_ID = re.compile(r"^[A-Za-z0-9_-]+\s*$")


def _get_auth_params() -> dict | None:
    """返回心知认证参数字典：key 或 uid+ts+ttl+sig。未配置返回 None。"""
    key = (os.environ.get("SENIVERSE_KEY") or SENIVERSE_KEY_DEFAULT or "").strip()
    if key:
        return {"key": key}


def _validate_location_chinese_only(location: str) -> str | None:
    """仅支持城市中文名。若为英文名、ID、经纬度等返回错误信息，否则返回 None。"""
    s = (location or "").strip()
    if not s:
        return "地点不能为空"
    if _LOCATION_LOOKS_LIKE_COORDS.match(s):
        return "仅支持城市中文名，不支持经纬度"
    if _LOCATION_LOOKS_LIKE_ID.match(s):
        return "仅支持城市中文名，不支持英文名或城市 ID"
    if not _LOCATION_ZH.search(s):
        return "仅支持城市中文名"
    return None


def _parse_single_date(s: str) -> date | None:
    """解析单个 yyyy-MM-dd，返回 date 或 None。"""
    s = (s or "").strip()
    if not s or not _DATE_PATTERN.match(s):
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _normalize_time_range_input(time_range_raw: str | list[str]) -> str:
    """将时间范围规范为字符串：str 原样 strip；list 取前 1～2 个元素用逗号拼接。"""
    if isinstance(time_range_raw, list):
        parts = [str(x).strip() for x in time_range_raw[:2] if x is not None]
        parts = [p for p in parts if p]
        return ",".join(parts) if parts else ""
    return (time_range_raw or "").strip()


def _parse_time_range_standard(time_range_raw: str) -> tuple[date, date] | None:
    """解析标准格式：yyyy-MM-dd,yyyy-MM-dd 或 yyyy-MM-dd。返回 (start_date, end_date) 或 None。"""
    raw = (time_range_raw or "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",", 1)]
    start_s = parts[0]
    end_s = parts[1] if len(parts) > 1 else start_s
    start_d = _parse_single_date(start_s)
    end_d = _parse_single_date(end_s)
    if start_d is None or end_d is None:
        return None
    if start_d > end_d:
        start_d, end_d = end_d, start_d
    return start_d, end_d


def _time_range_to_seniverse(
    start_date: date, end_date: date
) -> tuple[int | str, int]:
    """将 (start_date, end_date) 转为心知 daily 的 start 与 days。"""
    today = date.today()
    delta_start = (start_date - today).days
    days = (end_date - start_date).days + 1
    days = max(1, min(WEATHER_MAX_DAYS, days))
    if -2 <= delta_start <= 2:
        start: int | str = delta_start
    else:
        start = f"{start_date.year}/{start_date.month}/{start_date.day}"
    return start, days


def parse_query_type_from_str(s: str) -> set[str]:
    """解析查询类型字符串：weather、air、both（或 all）；未传或空时默认 weather。CLI 与 run_weather_search 共用。"""
    raw = (s or "").strip().lower()
    if not raw:
        return {"weather"}
    if raw in ("both", "all"):
        return {"weather", "air"}
    out = set()
    for part in raw.replace(",", " ").split():
        part = part.strip()
        if part in ("weather", "天气"):
            out.add("weather")
        elif part in ("air", "空气", "空气质量"):
            out.add("air")
    return out if out else {"weather"}



def _air_window_overlaps_request(
    start_date: date, end_date: date
) -> tuple[bool, date, date]:
    """
    空气接口仅支持未来 N 天。判断请求范围 [start_date, end_date] 是否与有效窗口 [today, today+ N-1] 有重叠。
    返回 (是否重叠, 有效窗口起始日, 有效窗口结束日)。
    """
    today = date.today()
    window_end = today + timedelta(days=AIR_VALID_DAYS - 1)
    if end_date < today or start_date > window_end:
        return False, today, window_end
    return True, today, window_end


def _filter_air_to_requested_days(
    air: dict,
    start_date: date,
    end_date: date,
    window_start: date,
    window_end: date,
) -> dict:
    """
    将空气数据按「请求范围内且在未来 N 天内」的天数筛选，不需要的去掉。
    若 air 内含按日列表（如 daily 且每项有 date），则只保留在 [start_date, end_date] 与 [window_start, window_end] 交集中的日期。
    """
    if not air or not isinstance(air, dict):
        return air
    want_start = max(start_date, window_start)
    want_end = min(end_date, window_end)
    want_dates = set()
    d = want_start
    while d <= want_end:
        want_dates.add(d.isoformat())
        d += timedelta(days=1)
    # 按日结构：daily 列表，每项有 date 字段（可能为 yyyy-MM-dd 或带时间）
    if "daily" in air and isinstance(air["daily"], list):
        def _norm_date(v):
            if v is None:
                return None
            s = str(v).strip()[:10]
            return s if len(s) == 10 else None
        filtered = [
            x for x in air["daily"]
            if _norm_date(x.get("date")) in want_dates
        ]
        return {**air, "daily": filtered}
    # 若为单条实况（无 daily），直接返回
    return air




@trace_call
async def run_weather_search(
    location: str,
    time_range: str | list[str] | None = None,
    *,
    http_client: Any,
    query: str | set[str] | None = None,
    language: str = DEFAULT_LANGUAGE,
    unit: str = DEFAULT_UNIT,
    auth: dict | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    天气查询主入口（函数调用）。由调用方传入 http_client（CLI 在 run_weather_search 中创建）。

    参数：
      location: 地点（城市中文名）。
      time_range: 时间范围。可为字符串（yyyy-MM-dd,yyyy-MM-dd 或 yyyy-MM-dd）或列表（如 ["2026-03-17"] 或 ["2026-03-17", "2026-03-19"]）。
      query: 可选，weather/air/both（字符串）或集合，默认 {"weather"}。
      language: 可选，语言。
      unit: 可选，单位。
      auth: 可选，心知认证参数；为 None 时从环境变量读取。

    返回：
      成功：{"success": True, "result": {...}}；
      失败：{"success": False, "error": "..."}。
    """
    init_logger("weather_search")
    hc = http_client
    # 兼容旧参数名：time_range_raw / query_type
    if time_range is None and kwargs.get("time_range_raw") is not None:
        time_range = kwargs.get("time_range_raw")
    if query is None and kwargs.get("query_type") is not None:
        query = kwargs.get("query_type")

    if query is None:
        query_type = {"weather"}
    elif isinstance(query, str):
        query_type = parse_query_type_from_str(query)
    else:
        query_type = set(query)
    auth = auth if auth is not None else _get_auth_params()
    if not auth:
        return _error_out(
            "未配置心知认证：请设置环境变量 SENIVERSE_KEY（私钥）或 SENIVERSE_UID + SENIVERSE_PRIVATE_KEY（签名）"
        )

    loc_err = _validate_location_chinese_only(location)
    if loc_err:
        return _error_out(loc_err)

    time_str = _normalize_time_range_input(time_range)
    if not time_str:
        return _error_out(
            "缺少时间范围。请使用标准格式 yyyy-MM-dd,yyyy-MM-dd 或 yyyy-MM-dd，或列表 [\"yyyy-MM-dd\"] / [\"yyyy-MM-dd\", \"yyyy-MM-dd\"]"
        )

    parsed = _parse_time_range_standard(time_str)
    if parsed is None:
        return _error_out(
            "无法解析时间范围：" + time_str + "。请使用标准格式 yyyy-MM-dd,yyyy-MM-dd 或 yyyy-MM-dd"
        )

    start_date, end_date = parsed
    today = date.today()
    weather_window_start = today + timedelta(days=WEATHER_WINDOW_START_OFFSET)
    weather_window_end = today + timedelta(days=WEATHER_WINDOW_END_DAYS)

    result_location = {"name": location, "id": ""}
    daily_list: list = []
    air: dict = {}

    weather_had_overlap = False
    if "weather" in query_type:
        w_start = max(start_date, weather_window_start)
        w_end = min(end_date, weather_window_end)
        if w_start <= w_end:
            weather_had_overlap = True
            start_param, days_req = _time_range_to_seniverse(w_start, w_end)
            loc_daily, daily_list = await fetch_daily(
                location,
                auth,
                start_param,
                days_req,
                language,
                unit,
                http_client=hc,
            )
            if loc_daily:
                result_location = {
                    "name": (loc_daily or {}).get("name") or location,
                    "id": (loc_daily or {}).get("id", ""),
                }
            if daily_list:
                pass  # weather_api_ok
            def _daily_in_range(d: dict) -> bool:
                dt = (d.get("date") or "")[:10]
                if len(dt) != 10:
                    return False
                try:
                    d_date = datetime.strptime(dt, "%Y-%m-%d").date()
                    return start_date <= d_date <= end_date
                except ValueError:
                    return False
            daily_list = [d for d in (daily_list or []) if _daily_in_range(d)]
        if not daily_list and "air" not in query_type:
            reason = (
                "请求时间范围与天气支持范围（昨天至未来15天）无重叠，无法查询。"
                if not weather_had_overlap
                else f"该地点逐日预报接口未返回数据或返回异常: {location}"
            )
            return _error_out(f"无法获取该地点的逐日预报: {location}。原因: {reason}")

    air_had_overlap = False
    if "air" in query_type:
        overlaps, window_start, window_end = _air_window_overlaps_request(
            start_date, end_date
        )
        air_had_overlap = overlaps
        if overlaps:
            air = await fetch_air(location, auth, language, http_client=hc)
            air = _filter_air_to_requested_days(
                air, start_date, end_date, window_start, window_end
            )

    if not daily_list and not air:
        reasons = []
        if "weather" in query_type and not daily_list:
            reasons.append(
                "逐日天气: 请求时间与支持范围（昨天至未来15天）无重叠或接口未返回数据"
            )
        if "air" in query_type and not air:
            reasons.append(
                "空气质量: 请求时间与支持范围（今天至未来5天）无重叠或接口未返回数据"
            )
        reason_str = "；".join(reasons) if reasons else "接口未返回数据"
        return _error_out(f"无法获取该地点的数据: {location}。原因: {reason_str}")

    uncovered_notes: list[str] = []
    if start_date < weather_window_start and "weather" in query_type:
        end_uncovered = min(end_date, weather_window_start - timedelta(days=1))
        uncovered_notes.append(
            f"天气逐日仅支持昨天至未来15天，请求中的 {start_date.isoformat()} 至 {end_uncovered.isoformat()} 未覆盖，未返回该段逐日预报。"
        )
    if end_date > weather_window_end and "weather" in query_type:
        start_uncovered = max(start_date, weather_window_end + timedelta(days=1))
        uncovered_notes.append(
            f"天气逐日仅支持昨天至未来15天，请求中的 {start_uncovered.isoformat()} 至 {end_date.isoformat()} 未覆盖，未返回该段逐日预报。"
        )
    air_window_end = today + timedelta(days=AIR_VALID_DAYS - 1)
    if "air" in query_type:
        if start_date < today:
            end_air_uncovered = min(end_date, today - timedelta(days=1))
            uncovered_notes.append(
                f"空气质量仅支持今天至未来5天，请求中的 {start_date.isoformat()} 至 {end_air_uncovered.isoformat()} 未覆盖，未返回该段空气质量。"
            )
        if end_date > air_window_end:
            start_air_uncovered = max(start_date, air_window_end + timedelta(days=1))
            uncovered_notes.append(
                f"空气质量仅支持今天至未来5天，请求中的 {start_air_uncovered.isoformat()} 至 {end_date.isoformat()} 未覆盖，未返回该段空气质量。"
            )

    result = {
        "location": result_location,
        "daily": daily_list,
        "air": air,
        "time_range": [start_date.isoformat(), end_date.isoformat()],
    }
    if uncovered_notes:
        result["uncovered_note"] = uncovered_notes
    empty_reasons = []
    if "weather" in query_type and not daily_list:
        if not weather_had_overlap:
            empty_reasons.append(
                "逐日预报：请求时间与天气支持范围（昨天至未来15天）无重叠，故无数据。"
            )
        else:
            empty_reasons.append("逐日预报：该地点接口未返回数据或返回异常。")
    if "air" in query_type and not air:
        if not air_had_overlap:
            empty_reasons.append(
                "空气质量：请求时间与支持范围（今天至未来5天）无重叠，故无数据。"
            )
        else:
            empty_reasons.append("空气质量：该地点接口未返回数据或返回异常。")
    if empty_reasons:
        result["empty_reason"] = "；".join(empty_reasons)
    return {"success": True, "result": result}


