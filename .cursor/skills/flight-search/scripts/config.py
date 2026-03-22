#!/usr/bin/env python3
"""
航班查询统一配置。所有魔法值集中在此，便于维护。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 将本 skill 的 scripts 目录加入 path，便于 `from client` / `from features` 等导入
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# ---------- API ----------
API_URL = "https://apis.juhe.cn/flight/query"
# API Key：在此直接填写，或留空后由环境变量 API_KEY_ENV 提供
API_KEY = "6067b93001e47645ff3a51a51c005cc7"
API_KEY_ENV = "JUHE_FLIGHT_API_KEY"
API_TIMEOUT_SECONDS = 15

# ---------- 数据目录 ----------
DATA_DIR_ENV = "FLIGHT_DATA_DIR"
_SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR_DEFAULT = _SKILL_DIR / "references"

# ---------- 默认行为 ----------
DEFAULT_MAX_SEGMENTS = "1"
# 输出航班数量上限：-1 表示不限制，正整数表示最多返回几条
MAX_OUTPUT_FLIGHTS = 5
# 为 True 时仅返回直飞，且从每条航班中移除 segments、transferNum 等无用字段
DIRECT_ONLY = False
# 为 True 时 flightInfo 为 Markdown 表格字符串以节省 token；为 False 时为 JSON 数组
FLIGHTS_AS_MARKDOWN = True

# ---------- 时间格式 ----------
DATETIME_FMT = "%Y-%m-%d %H:%M"
DATE_FMT = "%Y-%m-%d"
