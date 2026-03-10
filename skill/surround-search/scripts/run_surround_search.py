#!/usr/bin/env python3
"""
周边搜索主入口：地理编码 → 周边搜索 → 统一结果。
用法：
  python run_surround_search.py <目标地址> --keyword <搜索项> [--city 城市]
环境变量：AMAP_KEY（高德 Web 服务 API Key）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

from config import (
    AROUND_URL,
    API_KEY,
    API_KEY_ENV,
    DEFAULT_MAX_RESULTS,
    DEFAULT_RADIUS,
    GEOCODE_URL,
    REQUEST_TIMEOUT_SECONDS,
)


def _ensure_utf8_io() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _get_key() -> str | None:
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key and API_KEY:
        key = (API_KEY or "").strip()
    return key or None


def _http_get(url: str, params: dict) -> dict:
    req = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params),
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def geocode(key: str, address: str, city: str | None) -> dict:
    """高德地理编码，返回第一条结果的坐标 (lng,lat) 或 None。"""
    params = {"key": key, "address": address}
    if city:
        params["city"] = city
    data = _http_get(GEOCODE_URL, params)
    geocodes = data.get("geocodes")
    if data.get("status") != "1" or not isinstance(geocodes, list) or len(geocodes) == 0:
        return {"ok": False, "info": data.get("info", "未知错误")}
    first = geocodes[0]
    if not isinstance(first, dict):
        return {"ok": False, "info": "无坐标"}
    loc = first.get("location")
    if not loc or not isinstance(loc, str):
        return {"ok": False, "info": "无坐标"}
    return {"ok": True, "location": loc}


def around(
    key: str,
    location: str,
    keywords: str,
    city: str | None,
    radius: int,
    page: int = 1,
) -> dict:
    """高德周边搜索。location 为 "经度,纬度"。不传 offset、sortrule，使用 API 默认。"""
    params = {
        "key": key,
        "location": location,
        "radius": min(max(0, radius), 50000) or DEFAULT_RADIUS,
        "keywords": keywords,
        "page": max(1, page),
    }
    if city:
        params["city"] = city
    return _http_get(AROUND_URL, params)


def integrate_pois(amap_pois: list) -> list:
    """将高德 pois 转为统一结构。"""
    out = []
    for p in amap_pois or []:
        if not isinstance(p, dict):
            continue
        loc = p.get("location") or ""
        if "," in loc:
            parts = loc.split(",", 1)
            try:
                loc_obj = {"lng": float(parts[0].strip()), "lat": float(parts[1].strip())}
            except ValueError:
                loc_obj = None
        else:
            loc_obj = None
        dist = p.get("distance")
        if dist is not None and dist != "":
            try:
                dist = int(float(dist))
            except (ValueError, TypeError):
                dist = None
        out.append({
            "name": p.get("name") or "",
            "address": p.get("address") or ((p.get("pname") or "") + (p.get("cityname") or "") + (p.get("adname") or "")),
            "distance": dist,
            "poi_type": p.get("type") or "",
            "location": loc_obj,
        })
    return out


def _clarification_output(missing: list[str], error: str) -> None:
    out = {
        "success": False,
        "pois": [],
        "total_count": 0,
        "needs_clarification": True,
        "missing_params": missing,
        "error": error,
    }
    print(json.dumps(out, ensure_ascii=False))


def main() -> None:
    _ensure_utf8_io()
    parser = argparse.ArgumentParser(description="周边搜索：地理编码 + 周边搜索")
    parser.add_argument("location", nargs="?", default="", help="目标地址，如 北京西站、三里屯")
    parser.add_argument("--city", default=None, help="城市名，如 北京")
    parser.add_argument("--keyword", default=None, help="搜索项（必选），即用户要搜索的内容，如 餐厅、咖啡店")
    args = parser.parse_args()

    key = _get_key()
    if not key:
        out = {
            "success": False,
            "pois": [],
            "total_count": 0,
            "error": f"未配置 API Key，请设置环境变量 {API_KEY_ENV} 或在 config.py 中配置 API_KEY",
        }
        print(json.dumps(out, ensure_ascii=False))
        return

    location_str = (args.location or "").strip()
    keyword_str = (args.keyword or "").strip()
    missing = []
    if not location_str:
        missing.append("location")
    if not keyword_str:
        missing.append("keyword")
    if missing:
        _clarification_output(
            missing,
            "缺少必选参数：目标地址、搜索项。请补充后再调用。",
        )
        return

    # 1) 地理编码
    geo = geocode(key, location_str, args.city)
    if not geo.get("ok"):
        out = {
            "success": False,
            "pois": [],
            "total_count": 0,
            "query_summary": {"location": location_str, "city": args.city},
            "error": "地理编码失败：" + (geo.get("info") or "未找到目标地址"),
        }
        print(json.dumps(out, ensure_ascii=False))
        return

    center = geo["location"]
    radius = DEFAULT_RADIUS

    # 2) 周边搜索（不传 offset、sortrule，使用 API 默认）
    try:
        around_resp = around(
            key,
            center,
            keyword_str,
            args.city,
            radius=radius,
        )
    except Exception as e:
        out = {
            "success": False,
            "pois": [],
            "total_count": 0,
            "query_summary": {"location": location_str, "city": args.city, "keyword": keyword_str},
            "error": "周边搜索请求异常：" + str(e),
        }
        print(json.dumps(out, ensure_ascii=False))
        return

    if around_resp.get("status") != "1":
        out = {
            "success": False,
            "pois": [],
            "total_count": 0,
            "query_summary": {"location": location_str, "city": args.city, "keyword": keyword_str},
            "error": "周边搜索失败：" + (around_resp.get("info") or "未知错误"),
        }
        print(json.dumps(out, ensure_ascii=False))
        return

    amap_pois = around_resp.get("pois") or []
    pois = integrate_pois(amap_pois)
    if DEFAULT_MAX_RESULTS != -1 and len(pois) > DEFAULT_MAX_RESULTS:
        pois = pois[:DEFAULT_MAX_RESULTS]

    total = len(pois)
    out = {
        "success": True,
        "pois": pois,
        "total_count": total,
        "query_summary": {
            "location": location_str,
            "city": args.city,
            "keyword": keyword_str,
        },
    }
    if total == 0:
        out["message"] = (
            "未找到符合条件的周边结果。可能原因：该地址附近暂无此类场所；"
            "或可尝试更换搜索项、补充或修正目标地址后重试。"
        )
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        out = {
            "success": False,
            "pois": [],
            "total_count": 0,
            "error": "运行异常：" + str(e),
        }
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)
