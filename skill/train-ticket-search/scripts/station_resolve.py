#!/usr/bin/env python3
"""
根据 reference/station.json 从地址字符串中解析出唯一站点。
规则：JSON 的 key 在地址中匹配 → 取所有匹配；若多个匹配则按 (station_name, station_city) 去重，
再按匹配起始位置降序，返回最靠后（最右）的匹配结果。
"""
from __future__ import annotations

import json
from typing import Any

from config import STATION_JSON_PATH

_stations_cache: dict[str, dict[str, Any]] | None = None


def load_stations() -> dict[str, dict[str, Any]]:
    """加载 station.json，键为站点名。"""
    global _stations_cache
    if _stations_cache is not None:
        return _stations_cache
    if not STATION_JSON_PATH.is_file():
        _stations_cache = {}
        return _stations_cache
    with open(STATION_JSON_PATH, "r", encoding="utf-8") as f:
        _stations_cache = json.load(f)
    return _stations_cache


def resolve_station(address: str, stations: dict[str, dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """
    从地址字符串中解析出唯一站点。
    - 若不存在任何 JSON key 出现在 address 中 → 返回 None（参数不正确）。
    - 若存在多个匹配：先按 (station_name, station_city) 去重（同城同名保留一处），
      再按在 address 中的匹配起始位置降序排序，返回最靠后的匹配结果（即最右侧匹配）。
    """
    if not address or not isinstance(address, str):
        return None
    address = address.strip()
    if not address:
        return None
    if stations is None:
        stations = load_stations()
    if not stations:
        return None

    # 收集所有在 address 中出现的 key，及其最靠后的起始位置
    matches: list[tuple[str, int, dict[str, Any]]] = []
    for key, info in stations.items():
        if not key:
            continue
        pos = address.find(key)
        if pos == -1:
            continue
        # 同一 key 可能出现多次，取最靠后的起始位置
        last_pos = pos
        start = 0
        while True:
            i = address.find(key, start)
            if i == -1:
                break
            last_pos = i
            start = i + 1
        if not isinstance(info, dict):
            continue
        name = info.get("station_name") if isinstance(info.get("station_name"), str) else key
        city = info.get("station_city") if isinstance(info.get("station_city"), str) else ""
        matches.append((key, last_pos, {"station_name": name, "station_city": city, **info}))

    if not matches:
        return None

    # 按 (station_name, station_city) 去重：同一 (name, city) 只保留一处，保留位置最靠后的
    seen: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    for key, pos, info in matches:
        name = info.get("station_name", key)
        city = info.get("station_city", "")
        k = (name, city)
        if k not in seen or seen[k][0] < pos:
            seen[k] = (pos, info)

    # 按匹配起始位置降序；同位置时按 station_name 长度降序（更长更具体，如「北京南」优于「北京」）
    by_pos = sorted(seen.values(), key=lambda x: (x[0], len(x[1].get("station_name", ""))), reverse=True)
    return by_pos[0][1] if by_pos else None
