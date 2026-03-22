#!/usr/bin/env python3
"""
列车班次查询统一配置。所有魔法值集中在此，便于维护。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 将本 skill 的 scripts 目录加入 path，便于 `from client` / `from features` 等导入
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# ---------- API ----------
TRAIN_API_URL = "https://apis.juhe.cn/fapigw/train/query"
API_KEY_ENV = "JUHE_TRAIN_API_KEY"
# API Key：可在此配置，未配置时从环境变量 API_KEY_ENV 读取
API_KEY = "6c1f41992d79304061d68e2d3c981adc"
DEBUG_ENV = "JUHE_TRAIN_DEBUG"
API_TIMEOUT_SECONDS = 15
API_SEARCH_TYPE = "1"
API_ENABLE_BOOKING_DEFAULT = "2"

# 出发时段（与聚合 API 一致）：凌晨/上午/下午/晚上
DEPARTURE_TIME_RANGE_OPTIONS = ("凌晨", "上午", "下午", "晚上")

# 时段名称 → (起始分钟, 结束分钟)，左闭右开
TIME_RANGE_MINUTES = {
    "凌晨": (0, 6 * 60),
    "上午": (6 * 60, 12 * 60),
    "下午": (12 * 60, 18 * 60),
    "晚上": (18 * 60, 24 * 60),
}
TIME_RANGE_OPTIONS = frozenset(TIME_RANGE_MINUTES)

# ---------- 车型与排序 ----------
TRAIN_TYPE_PREFIX = frozenset("G D Z T K O F S".split())
SORT_OPTIONS = {
    "price_asc", "price_desc",
    "departure_asc", "departure_desc",
    "arrival_asc", "arrival_desc",
    "duration_asc", "duration_desc",
}

# ---------- 运行默认值 ----------
# 输出数量限制：最多返回条数，-1 表示不限制
DEFAULT_MAX_RESULTS = 5
# True：支持自然语言时间并在脚本内用 jionlp 转化；False：仅接受固定格式 yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm
PARSE_NATURAL_LANGUAGE_TIME = False
# 为 True 时 trains 为 Markdown 表格字符串以节省 token；为 False 时为车次对象数组（命令行 --trains-format json 可覆盖）
TRAINS_AS_MARKDOWN = True

# ---------- 站点表 ----------
_SKILL_ROOT = Path(__file__).resolve().parent.parent
STATION_JSON_PATH = _SKILL_ROOT / "reference" / "station.json"
