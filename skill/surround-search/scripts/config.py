#!/usr/bin/env python3
"""
周边搜索统一配置。所有魔法值集中在此，便于维护。
API Key：优先从环境变量 API_KEY_ENV 读取，未设置时使用本文件中的 API_KEY。
"""
from __future__ import annotations

# ---------- API ----------
GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
AROUND_URL = "https://restapi.amap.com/v3/place/around"
API_KEY_ENV = "AMAP_KEY"
# 未设置环境变量时使用的 Key；留空则必须通过环境变量配置
API_KEY = "your-key"
REQUEST_TIMEOUT_SECONDS = 15

# ---------- 搜索默认 ----------
# 搜索半径（米），固定 5km，不向用户暴露
DEFAULT_RADIUS = 5000

# 返回条数上限：仅对脚本返回结果做截断，不传给 API。-1 表示不截断
DEFAULT_MAX_RESULTS = -1
