#!/usr/bin/env python3
"""
调用聚合数据航班查询 API。参数通过命令行长参数传入（整段 JSON）。
  python query_flight_api.py '{"departure":"SHA","arrival":"SIA","departureDate":"2025-12-21","maxSegments":"1"}'
输出：完整 API 响应的压缩 JSON；成功时 result 中含 flightInfo 与 flightCount；失败为 {"error":"..."}。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

from config import (
    API_KEY,
    API_KEY_ENV,
    API_TIMEOUT_SECONDS,
    API_URL,
    DEFAULT_MAX_SEGMENTS,
)


def _ensure_utf8_io() -> None:
    """避免 Windows 控制台 GBK 导致 print 报错或乱码，强制 stdout/stderr 使用 UTF-8。"""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def query(
    departure: str,
    arrival: str,
    departure_date: str,
    flight_no: str = "",
    max_segments: str | None = None,
    key: str | None = None,
) -> dict:
    max_segments = (max_segments or DEFAULT_MAX_SEGMENTS).strip() or DEFAULT_MAX_SEGMENTS
    key = (key or (API_KEY or os.environ.get(API_KEY_ENV) or "") or "").strip()
    if not key:
        return {"error": "缺少 API Key，请在 config.py 中配置 API_KEY 或设置环境变量 " + API_KEY_ENV, "error_code": -1}

    params = {
        "key": key,
        "departure": departure.strip().upper(),
        "arrival": arrival.strip().upper(),
        "departureDate": departure_date.strip(),
        "flightNo": (flight_no or "").strip(),
        "maxSegments": max_segments,
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8")
    except Exception as e:
        return {"error": str(e), "error_code": -2}

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        return {"error": f"API 返回非 JSON: {e}", "raw": body[:500], "error_code": -3}

    # 在结果中附带航班数量，便于展示「共 N 班」
    if data.get("error_code") == 0 and isinstance(data.get("result"), dict):
        flight_info = data["result"].get("flightInfo")
        data["result"]["flightCount"] = len(flight_info) if isinstance(flight_info, list) else 0

    return data


def main() -> None:
    _ensure_utf8_io()
    if not sys.argv[1:]:
        print(json.dumps({"error": "缺少输入：请将 JSON 作为命令行参数传入", "error_code": -1}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    raw = " ".join(sys.argv[1:]).strip()
    try:
        if raw.startswith("{"):
            opts = json.loads(raw)
        else:
            opts = {}
    except json.JSONDecodeError:
        opts = {}

    departure = opts.get("departure", "")
    arrival = opts.get("arrival", "")
    departure_date = opts.get("departureDate", "")
    if not departure or not arrival or not departure_date:
        print(
            json.dumps(
                {"error": "缺少必填参数: departure, arrival, departureDate", "error_code": -1},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    result = query(
        departure=departure,
        arrival=arrival,
        departure_date=departure_date,
        flight_no=opts.get("flightNo", ""),
        max_segments=opts.get("maxSegments") or DEFAULT_MAX_SEGMENTS,
    )
    # 压缩输出，无缩进与空行，节省 token
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
