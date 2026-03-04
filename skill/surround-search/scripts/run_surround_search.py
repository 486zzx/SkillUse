#!/usr/bin/env python3
"""
周边搜索主入口：地理编码 → 周边 POI → 统一结果。
用法：
  python run_surround_search.py <目标地址> [--city 城市] [--keyword 关键词] [--sort-by distance|weight] [--radius 米] [--max-results N]
环境变量：AMAP_KEY（高德 Web 服务 API Key）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
AROUND_URL = "https://restapi.amap.com/v3/place/around"
DEFAULT_RADIUS = 5000
MAX_OFFSET = 25


def _ensure_utf8_io() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _get_key() -> str | None:
    return os.environ.get("AMAP_KEY", "your-key").strip()


def _http_get(url: str, params: dict) -> dict:
    req = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params),
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
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
    keywords: str | None,
    city: str | None,
    radius: int,
    sortrule: str,
    offset: int,
    page: int = 1,
) -> dict:
    """高德周边搜索。location 为 "经度,纬度"。"""
    params = {
        "key": key,
        "location": location,
        "radius": min(max(0, radius), 50000) or 5000,
        "sortrule": "distance" if sortrule == "distance" else "weight",
        "offset": min(max(1, offset), MAX_OFFSET),
        "page": max(1, page),
    }
    if keywords:
        params["keywords"] = keywords
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


def main() -> None:
    _ensure_utf8_io()
    parser = argparse.ArgumentParser(description="周边搜索：地理编码 + 高德周边 POI")
    parser.add_argument("location", help="目标地址，如 北京西站、三里屯")
    parser.add_argument("--city", default=None, help="城市名，如 北京")
    parser.add_argument("--keyword", default=None, help="搜索关键词，如 餐厅、咖啡店")
    parser.add_argument("--sort-by", default="distance", choices=["distance", "weight"], dest="sort_by", help="排序：distance 或 weight")
    parser.add_argument("--radius", type=int, default=DEFAULT_RADIUS, help="搜索半径(米)，0-50000")
    parser.add_argument("--max-results", type=int, default=25, dest="max_results", help="返回条数上限，不传时默认25；建议≤25（高德单页限制）")
    args = parser.parse_args()

    key = _get_key()
    if not key:
        out = {
            "success": False,
            "pois": [],
            "total_count": 0,
            "error": "未设置环境变量 AMAP_KEY，请配置高德 Web 服务 API Key",
        }
        print(json.dumps(out, ensure_ascii=False))
        return

    location_str = (args.location or "").strip()
    if not location_str:
        out = {
            "success": False,
            "pois": [],
            "total_count": 0,
            "error": "目标地址不能为空",
        }
        print(json.dumps(out, ensure_ascii=False))
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
    radius = args.radius if 0 < args.radius <= 50000 else DEFAULT_RADIUS
    offset = min(args.max_results, MAX_OFFSET) if args.max_results > 0 else 25

    # 2) 周边搜索
    try:
        around_resp = around(
            key,
            center,
            args.keyword,
            args.city,
            radius=radius,
            sortrule=args.sort_by,
            offset=offset,
        )
    except Exception as e:
        out = {
            "success": False,
            "pois": [],
            "total_count": 0,
            "query_summary": {"location": location_str, "city": args.city, "keyword": args.keyword},
            "error": "周边搜索请求异常：" + str(e),
        }
        print(json.dumps(out, ensure_ascii=False))
        return

    if around_resp.get("status") != "1":
        out = {
            "success": False,
            "pois": [],
            "total_count": 0,
            "query_summary": {"location": location_str, "city": args.city, "keyword": args.keyword},
            "error": "周边搜索失败：" + (around_resp.get("info") or "未知错误"),
        }
        print(json.dumps(out, ensure_ascii=False))
        return

    amap_pois = around_resp.get("pois") or []
    pois = integrate_pois(amap_pois)
    if args.max_results > 0 and len(pois) > args.max_results:
        pois = pois[: args.max_results]

    out = {
        "success": True,
        "pois": pois,
        "total_count": len(pois),
        "query_summary": {
            "location": location_str,
            "city": args.city,
            "keyword": args.keyword,
            "sort_by": args.sort_by,
            "radius": radius,
        },
    }
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
