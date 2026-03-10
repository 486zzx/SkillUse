# -*- coding: utf-8 -*-
"""
天气查询 skill 统一配置：API 地址、路径、默认值等，避免在业务代码中使用魔法值。
"""
from __future__ import annotations

import os
from pathlib import Path

# ----- 路径 -----
SCRIPT_DIR = Path(__file__).resolve().parent
REFS_DIR = SCRIPT_DIR.parent / "references"

# ----- 心知 API -----
BASE_URL = os.environ.get("WEATHER_API_BASE_URL", "https://api.seniverse.com")
NOW_PATH = "/v3/weather/now.json"
DAILY_PATH = "/v3/weather/daily.json"
SUGGESTION_PATH = "/v3/life/suggestion.json"
AIR_PATH = "/v3/air/now.json"

# ----- 认证（仅作兜底，优先使用环境变量） -----
SENIVERSE_KEY_DEFAULT = os.environ.get("SENIVERSE_KEY", "your-key").strip()

# ----- 请求默认 -----
DEFAULT_LANGUAGE = "zh-Hans"
DEFAULT_UNIT = "c"
DAILY_DAYS_MIN = 1
DAILY_DAYS_MAX = 15
# 本 skill 输出：时间范围由调用方传入标准格式，不做天数上限假定
REQUEST_TIMEOUT_SECONDS = 10

# ----- 天气（逐日）支持的时间：昨天、今天、未来15天 -----
# 即 [today-1, today+15]，共 17 天
WEATHER_WINDOW_START_OFFSET = -1   # 昨天
WEATHER_WINDOW_END_DAYS = 15       # 未来 15 天（从今天起）
WEATHER_MAX_DAYS = 1 + 1 + 15      # 17 天，用于单次请求天数上限

# ----- 空气质量支持的时间：今天、未来5天 -----
# 即 [today, today+5]，共 6 天
AIR_VALID_DAYS = 6

# ----- 签名（可选） -----
SIGNATURE_TTL = 300

# ----- 时间范围与自然语言转换 -----
# 是否在脚本内将自然语言时间（如「明天」）转为标准范围 [yyyy-MM-dd, yyyy-MM-dd]；默认关闭，调用方应传入标准格式
ENABLE_NATURAL_LANGUAGE_DATE_CONVERSION = os.environ.get(
    "WEATHER_ENABLE_NL_DATE_CONVERSION", "false"
).strip().lower() in ("1", "true", "yes")

AIR_SCOPE = "city"
