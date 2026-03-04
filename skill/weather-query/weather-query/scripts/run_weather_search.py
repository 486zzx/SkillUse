#!/usr/bin/env python3
"""
天气查询总入口：基于心知天气 API，地点 → 实况 + 逐日预报，可选生活指数与空气质量。
输入：位置参数（地点必填，日期可选）；可选 --days、--with-suggestion、--with-air。
用法：python run_weather_search.py 北京
      python run_weather_search.py 上海 明天 --days 5 --with-suggestion --with-air
输出：压缩 JSON。成功为 result；失败为 {"success":false,"error":"..."}
认证：环境变量 SENIVERSE_KEY（私钥）或 SENIVERSE_UID + SENIVERSE_PRIVATE_KEY（签名）。
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
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REFS_DIR = SCRIPT_DIR.parent / "references"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

BASE_URL = "https://api.seniverse.com"
NOW_PATH = "/v3/weather/now.json"
DAILY_PATH = "/v3/weather/daily.json"
SUGGESTION_PATH = "/v3/life/suggestion.json"
AIR_PATH = "/v3/air/now.json"

# 已获得的心知私钥（未设置环境变量 SENIVERSE_KEY 时使用）
SENIVERSE_KEY = "your-key"

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


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
    key = (os.environ.get("SENIVERSE_KEY") or SENIVERSE_KEY).strip()
    if key:
        return {"key": key}
    uid = os.environ.get("SENIVERSE_UID", "").strip()
    private = os.environ.get("SENIVERSE_PRIVATE_KEY", "").strip()
    if not uid or not private:
        return None
    ts = int(time.time())
    ttl = 300
    payload = f"ttl={ttl}&ts={ts}&uid={uid}"
    sig_binary = hmac.new(
        private.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    sig_b64 = base64.b64encode(sig_binary).decode("utf-8")
    sig = quote(sig_b64, safe="")
    return {"ts": ts, "ttl": ttl, "uid": uid, "sig": sig}


def _parse_args(argv: list[str]) -> tuple[str, str, int, bool, bool, str, str]:
    """解析 argv：地点、日期、days、with_suggestion、with_air、language、unit。"""
    args = [a for a in argv if a != ""]
    positionals = []
    days = 3
    with_suggestion = False
    with_air = False
    language = "zh-Hans"
    unit = "c"
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:].strip().lower()
            if key == "with-suggestion":
                with_suggestion = True
            elif key == "with-air":
                with_air = True
            elif key == "days" and i + 1 < len(args) and not args[i + 1].startswith("--"):
                try:
                    days = max(1, min(15, int(args[i + 1])))
                except ValueError:
                    days = 3
                i += 1
            elif key == "language" and i + 1 < len(args):
                language = args[i + 1].strip() or language
                i += 1
            elif key == "unit" and i + 1 < len(args):
                unit = args[i + 1].strip() or unit
                i += 1
            i += 1
            continue
        positionals.append(a)
        i += 1
    location = (positionals[0] or "").strip() if positionals else ""
    date_raw = (positionals[1] or "").strip() if len(positionals) > 1 else ""
    return location, date_raw, days, with_suggestion, with_air, language, unit


def _date_to_start(date_raw: str) -> int | str:
    """将用户输入的模糊时间字符串（原样传入）用 JioNLP 解析为心知 daily 的 start：0/1/2/-1/-2 或 yyyy/m/d。"""
    if not date_raw:
        return 0
    s = date_raw.strip()
    if not s:
        return 0

    today = date.today()
    parsed_date = _parse_date_with_jio(s, today)
    if parsed_date is not None:
        delta_days = (parsed_date - today).days
        if -2 <= delta_days <= 2:
            return delta_days
        return f"{parsed_date.year}/{parsed_date.month}/{parsed_date.day}"

    return _date_to_start_fallback(s)


def _parse_date_with_jio(text: str, base_date: date) -> date | None:
    """使用 JioNLP 解析时间字符串，返回 date 或 None。"""
    try:
        import jionlp as jio
    except ImportError:
        logger.debug("jionlp not installed, using fallback for date: %s", text)
        return None
    try:
        base_ts = datetime.combine(base_date, datetime.min.time()).timestamp()
        res = jio.parse_time(text, time_base=base_ts)
    except Exception as e:
        logger.debug("jionlp parse_time failed for %s: %s", text, e)
        return None
    if not res or "time" not in res:
        return None
    t = res["time"]
    if isinstance(t, list) and len(t) >= 1:
        first = t[0]
        if isinstance(first, str) and len(first) >= 10:
            try:
                return datetime.strptime(first[:10], "%Y-%m-%d").date()
            except ValueError:
                pass
    if isinstance(t, str) and len(t) >= 10:
        try:
            return datetime.strptime(t[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    return None


def _date_to_start_fallback(s: str) -> int | str:
    """jionlp 不可用或解析失败时的简单规则：今天/明天/后天/昨天/前天、yyyy-mm-dd。"""
    if s in ("今天", "today"):
        return 0
    if s in ("明天", "tomorrow"):
        return 1
    if s in ("后天",):
        return 2
    if s in ("昨天", "yesterday"):
        return -1
    if s in ("前天",):
        return -2
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if match:
        return f"{match.group(1)}/{int(match.group(2))}/{int(match.group(3))}"
    return 0


def _seniverse_get(path: str, params: dict, auth: dict) -> dict | None:
    """心知 GET 请求，合并 auth 与 params；返回 JSON 或 None。"""
    all_params = {**auth, **params}
    try:
        resp = requests.get(BASE_URL + path, params=all_params, timeout=10)
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


def _fetch_now(location: str, auth: dict, language: str, unit: str) -> tuple[dict | None, dict | None]:
    """拉取实况；返回 (location_info, now_data)，失败返回 (None, None) 或 error_info。"""
    data = _seniverse_get(
        NOW_PATH,
        {"location": location, "language": language, "unit": unit},
        auth,
    )
    if not data:
        return None, None
    err = _extract_error(data)
    if err:
        return None, {"error": err}
    results = data.get("results") or []
    if not results:
        return None, None
    r = results[0]
    loc = r.get("location") or {}
    now = r.get("now")
    return loc, now


def _fetch_daily(
    location: str,
    auth: dict,
    start: int | str,
    days: int,
    language: str,
    unit: str,
) -> tuple[dict | None, list]:
    """拉取逐日；返回 (location_info, daily_list)，失败时 daily_list 为空且 location_info 可能为 None。"""
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


def _fetch_suggestion(location: str, auth: dict, language: str) -> dict:
    """拉取生活指数；仅中国城市有效。返回 suggestion 对象或空 dict。"""
    data = _seniverse_get(
        SUGGESTION_PATH,
        {"location": location, "language": language},
        auth,
    )
    if not data or _extract_error(data):
        return {}
    results = data.get("results") or []
    if not results:
        return {}
    r = results[0]
    return r.get("suggestion") or {}


def _fetch_air(location: str, auth: dict, language: str) -> dict:
    """拉取空气质量；返回 air 对象或空 dict。"""
    data = _seniverse_get(
        AIR_PATH,
        {"location": location, "language": language, "scope": "city"},
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
            "error": "缺少参数：需要至少一个位置参数（地点），例如：run_weather_search.py 北京",
        })
        sys.exit(1)

    auth = _get_auth_params()
    if not auth:
        _out({
            "success": False,
            "error": "未配置心知认证：请设置环境变量 SENIVERSE_KEY（私钥）或 SENIVERSE_UID + SENIVERSE_PRIVATE_KEY（签名）",
        })
        sys.exit(1)

    location, date_raw, days, with_suggestion, with_air, language, unit = _parse_args(sys.argv[1:])
    if not location:
        _out({"success": False, "error": "地点不能为空"})
        sys.exit(1)

    start = _date_to_start(date_raw)
    loc_info, now_data = _fetch_now(location, auth, language, unit)
    if now_data is not None and now_data.get("error"):
        _out({"success": False, "error": now_data.get("error", "实况接口返回错误")})
        sys.exit(1)
    if loc_info is None and now_data is None:
        _out({"success": False, "error": f"无法获取地点或实况: {location}"})
        sys.exit(1)

    loc_daily, daily_list = _fetch_daily(location, auth, start, days, language, unit)
    location_merged = {**(loc_info or {}), **(loc_daily or {})}
    result_location = {
        "name": location_merged.get("name") or location,
        "id": location_merged.get("id", ""),
    }
    current = now_data if now_data else {}
    suggestion = _fetch_suggestion(location, auth, language) if with_suggestion else {}
    air = _fetch_air(location, auth, language) if with_air else {}

    result = {
        "location": result_location,
        "current": current,
        "daily": daily_list,
        "suggestion": suggestion,
        "air": air,
    }
    if date_raw:
        result["requested_date"] = date_raw
    _out({"success": True, "result": result})


if __name__ == "__main__":
    main()
