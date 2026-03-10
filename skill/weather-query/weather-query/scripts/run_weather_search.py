#!/usr/bin/env python3
"""
天气查询总入口：地点 + 时间范围（标准格式 yyyy-MM-dd,yyyy-MM-dd）+ query（选择天气/空气质量/两者）。
只接受标准格式时间范围，后端按各数据源支持的时间取重叠部分请求并筛选结果。
输入：位置参数 1=地点，2=时间范围（必填，标准格式 yyyy-MM-dd,yyyy-MM-dd 或 yyyy-MM-dd）；--query weather|air|both（默认 weather）。
输出：压缩 JSON。成功为 result；失败为 {"success":false,"error":"..."}。
认证与 API 配置见 config.py 与环境变量（仅代码内使用，不在 skill 文档中暴露）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config import (
    AIR_PATH,
    AIR_SCOPE,
    AIR_VALID_DAYS,
    BASE_URL,
    DAILY_PATH,
    DEFAULT_LANGUAGE,
    DEFAULT_UNIT,
    REQUEST_TIMEOUT_SECONDS,
    SENIVERSE_KEY_DEFAULT,
    SIGNATURE_TTL,
    WEATHER_MAX_DAYS,
    WEATHER_WINDOW_END_DAYS,
    WEATHER_WINDOW_START_OFFSET,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# 标准日期格式 yyyy-MM-dd
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 地点仅支持城市中文名：至少包含一个中文字符，拒绝纯英文/数字/经纬度/ID
_LOCATION_ZH = re.compile(r"[\u4e00-\u9fff]")
_LOCATION_LOOKS_LIKE_COORDS = re.compile(r"^\s*\d+\.?\d*\s*:\s*\d+\.?\d*\s*$")
_LOCATION_LOOKS_LIKE_ID = re.compile(r"^[A-Za-z0-9_-]+\s*$")


def _ensure_utf8_io() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _out(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


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


def _parse_query_type(s: str) -> set[str]:
    """解析 --query：weather、air、both（或 all）；未传或空时默认 weather。"""
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


def _parse_args(
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
                query_type = _parse_query_type(args[i + 1])
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


def _seniverse_get(path: str, params: dict, auth: dict) -> dict | None:
    """心知 GET 请求，合并 auth 与 params；返回 JSON 或 None。"""
    all_params = {**auth, **params}
    try:
        resp = requests.get(
            BASE_URL + path, params=all_params, timeout=REQUEST_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.exception("Seniverse request failed %s: %s", path, e)
        return None


def _extract_error(data: dict) -> str:
    """从心知错误响应中提取原因。"""
    if isinstance(data.get("status_code"), int) and data.get("status_code") != 200:
        return data.get("status") or data.get("message") or "API 返回错误"
    return ""


def _fetch_daily(
    location: str,
    auth: dict,
    start: int | str,
    days: int,
    language: str,
    unit: str,
) -> tuple[dict | None, list]:
    """拉取逐日；返回 (location_info, daily_list)。"""
    params = {
        "location": location,
        "language": language,
        "unit": unit,
        "start": start,
        "days": days,
    }
    data = _seniverse_get(DAILY_PATH, params, auth)
    if not data:
        return None, []
    results = data.get("results") or []
    if not results:
        return None, []
    r = results[0]
    loc = r.get("location") or {}
    daily = r.get("daily") or []
    return loc, daily


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


def _fetch_air(location: str, auth: dict, language: str) -> dict:
    """拉取空气质量；返回 air 对象或空 dict。"""
    data = _seniverse_get(
        AIR_PATH,
        {"location": location, "language": language, "scope": AIR_SCOPE},
        auth,
    )
    if not data or _extract_error(data):
        return {}
    results = data.get("results") or []
    if not results:
        return {}
    r = results[0]
    return r.get("air") or r


def main() -> None:
    _ensure_utf8_io()
    if len(sys.argv) < 2:
        _out({
            "success": False,
            "error": "缺少参数：需要至少地点与时间范围（标准格式），例如：run_weather_search.py 北京 2026-03-10,2026-03-12",
        })
        sys.exit(1)

    auth = _get_auth_params()
    if not auth:
        _out({
            "success": False,
            "error": "未配置心知认证：请设置环境变量 SENIVERSE_KEY（私钥）或 SENIVERSE_UID + SENIVERSE_PRIVATE_KEY（签名）",
        })
        sys.exit(1)

    location, time_range_raw, query_type, language, unit = _parse_args(sys.argv[1:])
    loc_err = _validate_location_chinese_only(location)
    if loc_err:
        _out({"success": False, "error": loc_err})
        sys.exit(1)

    if not time_range_raw:
        _out({
            "success": False,
            "error": "缺少时间范围。请使用标准格式 yyyy-MM-dd,yyyy-MM-dd 或 yyyy-MM-dd",
        })
        sys.exit(1)

    parsed = _parse_time_range_standard(time_range_raw)
    if parsed is None:
        _out({
            "success": False,
            "error": f"无法解析时间范围：{time_range_raw}。请使用标准格式 yyyy-MM-dd,yyyy-MM-dd 或 yyyy-MM-dd",
        })
        sys.exit(1)

    start_date, end_date = parsed
    today = date.today()
    weather_window_start = today + timedelta(days=WEATHER_WINDOW_START_OFFSET)
    weather_window_end = today + timedelta(days=WEATHER_WINDOW_END_DAYS)

    result_location = {"name": location, "id": ""}
    daily_list: list = []
    air: dict = {}

    # 天气逐日：仅当选择天气时请求，只请求与支持时间 [昨天, 今天+15天] 的重叠部分
    weather_had_overlap = False  # 请求范围是否与天气窗口有重叠
    weather_api_ok = False       # 是否成功请求到逐日数据
    if "weather" in query_type:
        w_start = max(start_date, weather_window_start)
        w_end = min(end_date, weather_window_end)
        if w_start <= w_end:
            weather_had_overlap = True
            start_param, days_req = _time_range_to_seniverse(w_start, w_end)
            loc_daily, daily_list = _fetch_daily(
                location, auth, start_param, days_req, language, unit
            )
            if loc_daily:
                result_location = {
                    "name": (loc_daily or {}).get("name") or location,
                    "id": (loc_daily or {}).get("id", ""),
                }
            if daily_list:
                weather_api_ok = True
            # 只保留落在用户请求区间 [start_date, end_date] 内的天数
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
            if daily_list:
                weather_api_ok = True
        if not daily_list and "air" not in query_type:
            reason = "请求时间范围与天气支持范围（昨天至未来15天）无重叠，无法查询。" if not weather_had_overlap else f"该地点逐日预报接口未返回数据或返回异常: {location}"
            _out({"success": False, "error": f"无法获取该地点的逐日预报: {location}。原因: {reason}"})
            sys.exit(1)

    # 空气质量：仅当选择空气且请求时间与支持窗口有重叠时请求，后处理筛选重叠天数
    air_had_overlap = False
    if "air" in query_type:
        overlaps, window_start, window_end = _air_window_overlaps_request(
            start_date, end_date
        )
        air_had_overlap = overlaps
        if overlaps:
            air = _fetch_air(location, auth, language)
            air = _filter_air_to_requested_days(
                air, start_date, end_date, window_start, window_end
            )

    if not daily_list and not air:
        reasons = []
        if "weather" in query_type and not daily_list:
            reasons.append("逐日天气: 请求时间与支持范围（昨天至未来15天）无重叠或接口未返回数据")
        if "air" in query_type and not air:
            reasons.append("空气质量: 请求时间与支持范围（今天至未来5天）无重叠或接口未返回数据")
        reason_str = "；".join(reasons) if reasons else "接口未返回数据"
        _out({"success": False, "error": f"无法获取该地点的数据: {location}。原因: {reason_str}"})
        sys.exit(1)

    # 未覆盖时间说明：若请求范围超出各数据源支持范围，在输出中说明
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
    # 逐日或空气质量为空时，合并说明原因
    empty_reasons: list[str] = []
    if "weather" in query_type and not daily_list:
        if not weather_had_overlap:
            empty_reasons.append("逐日预报：请求时间与天气支持范围（昨天至未来15天）无重叠，故无数据。")
        else:
            empty_reasons.append("逐日预报：该地点接口未返回数据或返回异常。")
    if "air" in query_type and not air:
        if not air_had_overlap:
            empty_reasons.append("空气质量：请求时间与支持范围（今天至未来5天）无重叠，故无数据。")
        else:
            empty_reasons.append("空气质量：该地点接口未返回数据或返回异常。")
    if empty_reasons:
        result["empty_reason"] = "；".join(empty_reasons)
    _out({"success": True, "result": result})


if __name__ == "__main__":
    main()
