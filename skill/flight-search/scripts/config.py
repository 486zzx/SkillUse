#!/usr/bin/env python3
"""
航班查询统一配置。所有魔法值集中在此，便于维护。
"""
from __future__ import annotations

from pathlib import Path

# ---------- API ----------
API_URL = "https://apis.juhe.cn/flight/query"
# API Key：在此直接填写，或留空后由环境变量 API_KEY_ENV 提供
API_KEY = "your-key"
API_KEY_ENV = "JUHE_FLIGHT_API_KEY"
API_TIMEOUT_SECONDS = 15

# ---------- 数据目录 ----------
DATA_DIR_ENV = "FLIGHT_DATA_DIR"
_SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR_DEFAULT = _SKILL_DIR / "references"

# ---------- 默认行为 ----------
DEFAULT_MAX_SEGMENTS = "1"
# 输出航班数量上限：-1 表示不限制，正整数表示最多返回几条
MAX_OUTPUT_FLIGHTS = -1
# True：脚本内支持自然语言→时间范围转化（如「明天」→ 当日 00:00–23:59）；False：仅接受标准格式
ENABLE_NLP_TIME_RANGE = False

# ---------- 时间格式 ----------
DATETIME_FMT = "%Y-%m-%d %H:%M"
DATE_FMT = "%Y-%m-%d"
