"""
周边搜索业务逻辑（features）：地理编码 → 周边搜索 → 统一结果。

  from features.surround_service import surround_search, normalize_surround_contract
环境变量：AMAP_KEY（高德 Web 服务 API Key）

命令行参数解析仅在 scripts/run_surround_search.py。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from skill_logging._log import init_logger, trace_call
from features.api_request import geocode, around_search
from config import API_KEY, API_KEY_ENV, DEFAULT_MAX_RESULTS, DEFAULT_RADIUS


def _get_key() -> str | None:
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key and API_KEY:
        key = (API_KEY or "").strip()
    return key or None


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


def normalize_surround_contract(
    raw: Any,
    *,
    address: str,
    keywords: str,
    city: str | None,
) -> dict:
    """
    统一 surround-search 对外返回口径（仅结构归一化，不改变业务语义）：
    - 必含：success, pois, total_count, query_summary, error
    """
    default_query = {"location": address or "", "city": city, "keyword": keywords or ""}
    if not isinstance(raw, dict):
        return {
            "success": False,
            "pois": [],
            "total_count": 0,
            "query_summary": default_query,
            "error": "返回格式异常：非对象",
        }

    data = dict(raw)
    # 兼容上层可能包一层 result 的调用形态
    if isinstance(data.get("result"), dict):
        nested = data.get("result") or {}
        merged = dict(data)
        merged.update(nested)
        data = merged

    success = bool(data.get("success", False))
    pois = data.get("pois")
    if not isinstance(pois, list):
        pois = []

    query_summary = data.get("query_summary")
    if not isinstance(query_summary, dict):
        query_summary = default_query
    else:
        query_summary = {
            "location": query_summary.get("location", address or ""),
            "city": query_summary.get("city", city),
            "keyword": query_summary.get("keyword", keywords or ""),
        }

    total_count = data.get("total_count")
    if not isinstance(total_count, int):
        total_count = len(pois)

    normalized = dict(data)
    normalized["success"] = success
    normalized["pois"] = pois
    normalized["total_count"] = total_count
    normalized["query_summary"] = query_summary
    normalized["error"] = str(data.get("error") or "")
    return normalized


@trace_call
async def surround_search(
    address: str,
    keywords: str,
    city: str | None = None,
    *,
    http_client: Any,
) -> dict:
    """
    周边搜索函数调用入口（参数名与 mcp_tools.json 对齐）。
    - address: 目标地址
    - keywords: 搜索项
    - city: 可选城市
    """
    init_logger("surround_search")
    hc = http_client
    key = _get_key()
    if not key:
        return {
            "success": False,
            "pois": [],
            "total_count": 0,
            "error": f"未配置 API Key，请设置环境变量 {API_KEY_ENV} 或在 config.py 中配置 API_KEY",
        }

    location_str = (address or "").strip()
    keyword_str = (keywords or "").strip()
    missing = []
    if not location_str:
        missing.append("address")
    if not keyword_str:
        missing.append("keywords")
    if missing:
        return {
            "success": False,
            "pois": [],
            "total_count": 0,
            "needs_clarification": True,
            "missing_params": missing,
            "error": "缺少必选参数：目标地址、搜索项。请补充后再调用。",
        }

    try:
        geo = await geocode(key, location_str, city, http_client=hc)
    except Exception as e:
        return {
            "success": False,
            "pois": [],
            "total_count": 0,
            "query_summary": {"location": location_str, "city": city},
            "error": f"地理编码请求异常：{e}",
        }
    if not geo.get("ok"):
        infocode = geo.get("infocode")
        info = geo.get("info") or "未找到目标地址"
        err = f"地理编码失败({infocode})：{info}" if infocode else f"地理编码失败：{info}"
        return {
            "success": False,
            "pois": [],
            "total_count": 0,
            "query_summary": {"location": location_str, "city": city},
            "error": err,
        }

    center = geo["location"]
    radius = DEFAULT_RADIUS
    try:
        around_resp = await around_search(
            key,
            center,
            keyword_str,
            city,
            radius=radius,
            http_client=hc,
        )
    except Exception as e:
        return {
            "success": False,
            "pois": [],
            "total_count": 0,
            "query_summary": {"location": location_str, "city": city, "keyword": keyword_str},
            "error": "周边搜索请求异常：" + str(e),
        }

    if str(around_resp.get("infocode")) != "10000":
        return {
            "success": False,
            "pois": [],
            "total_count": 0,
            "query_summary": {"location": location_str, "city": city, "keyword": keyword_str},
            "error": f"周边搜索失败({around_resp.get('infocode')})：{around_resp.get('info') or '未知错误'}",
        }

    amap_pois = around_resp.get("pois") or []
    pois = integrate_pois(amap_pois)
    if DEFAULT_MAX_RESULTS != -1 and len(pois) > DEFAULT_MAX_RESULTS:
        pois = pois[:DEFAULT_MAX_RESULTS]

    total = len(pois)
    out: dict[str, Any] = {
        "success": True,
        "pois": pois,
        "total_count": total,
        "query_summary": {
            "location": location_str,
            "city": city,
            "keyword": keyword_str,
        },
    }
    if total == 0:
        out["message"] = (
            "未找到符合条件的周边结果。可能原因：该地址附近暂无此类场所；"
            "或可尝试更换搜索项、补充或修正目标地址后重试。"
        )
    return out
