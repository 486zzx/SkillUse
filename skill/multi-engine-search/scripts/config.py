# -*- coding: utf-8 -*-
"""
多引擎聚合搜索统一配置。
权重与分类均从 reference/weights 下的 JSON 读取，不在代码中硬编码。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Union

# ---------------------------------------------------------------------------
# 环境变量名
# ---------------------------------------------------------------------------
ENV_AGGREGATE_ENGINES = "AGGREGATE_ENGINES"
ENV_AGGREGATE_LOG_PATH = "AGGREGATE_LOG_PATH"
ENV_AGGREGATE_TIMING = "AGGREGATE_TIMING"
ENV_WEIGHTS_DIR = "WEIGHTS_DIR"
ENV_BAIDU_APPBUILDER_API_KEY = "BAIDU_APPBUILDER_API_KEY"
ENV_TAVILY_API_KEY = "TAVILY_API_KEY"
ENV_ZHIPU_API_KEY = "ZHIPU_API_KEY"

# ---------------------------------------------------------------------------
# 默认值（仅用于：无权重文件时的引擎列表、RRF/融合的兜底常数）
# ---------------------------------------------------------------------------
DEFAULT_ENGINES = ["baidu", "tavily", "zhipu"]
DEFAULT_LOG_PATH = "aggregate_calls.jsonl"
DEFAULT_MAX_TOTAL_CHARS = 2500
DEFAULT_MAX_ITEMS = 50
"""多分类时各分类权重，None 表示等权。格式如 {"知识问答": 0.6, "新闻资讯": 0.4}。"""
DEFAULT_CATEGORY_WEIGHTS: Optional[Dict[str, float]] = None
PER_ITEM_MAX_CHARS_CAP = 12000
BM25_MIN_SCORE = 0.03
BM25_MIN_KEEP = 8
TOP_K_DEFAULT = 20
# 仅作 aggregate 入参默认值，实际分类以权重文件为准
DEFAULT_SEARCH_TYPE = "general"
# 搜索模式：快速 / 思考 / 专家，暂仅透传，后续可拓展用途
VALID_SEARCH_MODES = ("快速", "思考", "专家")
DEFAULT_SEARCH_MODE = "快速"

# ---------------------------------------------------------------------------
# 权重文件缓存（按需加载）
# ---------------------------------------------------------------------------
_WEIGHTS_DIR: Optional[Path] = None
_ENGINE_DATA: Optional[Dict] = None  # 完整 engine_weights_by_category.json
_DOMAIN_WEIGHTS_BY_CATEGORY: Optional[Dict] = None
_RERANK_POLICY: Optional[Dict] = None


def get_weights_dir() -> Path:
    """权重目录：环境变量 WEIGHTS_DIR 或 skill 根目录下的 reference/weights。"""
    global _WEIGHTS_DIR
    if _WEIGHTS_DIR is not None:
        return _WEIGHTS_DIR
    raw = os.environ.get(ENV_WEIGHTS_DIR, "").strip()
    if raw:
        _WEIGHTS_DIR = Path(raw)
    else:
        skill_root = Path(__file__).resolve().parent.parent
        _WEIGHTS_DIR = skill_root / "reference" / "weights"
    return _WEIGHTS_DIR


def _load_json(path: Path) -> Optional[Dict]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _ensure_weights_loaded() -> None:
    global _ENGINE_DATA, _DOMAIN_WEIGHTS_BY_CATEGORY, _RERANK_POLICY
    if _ENGINE_DATA is not None and _DOMAIN_WEIGHTS_BY_CATEGORY is not None:
        return
    wd = get_weights_dir()
    if _ENGINE_DATA is None:
        _ENGINE_DATA = _load_json(wd / "engine_weights_by_category.json") or {}
    if _DOMAIN_WEIGHTS_BY_CATEGORY is None:
        data = _load_json(wd / "domain_weights_by_category.json")
        _DOMAIN_WEIGHTS_BY_CATEGORY = (data or {}).get("by_category", {})
    if _RERANK_POLICY is None:
        _RERANK_POLICY = _load_json(wd / "rerank_policy.json") or {}


def _by_category() -> Dict:
    _ensure_weights_loaded()
    return (_ENGINE_DATA or {}).get("by_category", {})


def _aliases() -> Dict[str, str]:
    _ensure_weights_loaded()
    return (_ENGINE_DATA or {}).get("aliases", {})


def resolve_category(search_type: str) -> str:
    """
    解析为权重文件中的分类：先查 by_category 键，再查 aliases，否则原样返回。
    分类不虚构，仅来自权重文件。
    """
    st = (search_type or "").strip()
    by_cat = _by_category()
    if st in by_cat:
        return st
    alias = _aliases().get(st)
    if alias and alias in by_cat:
        return alias
    return st


def get_categories() -> List[str]:
    """权重文件中定义的所有分类（by_category 的键）。"""
    return list(_by_category().keys())


def get_resolved_categories(search_type: Union[str, List[str]]) -> List[str]:
    """将 search_type（单分类或多分类）解析为分类名列表，供输出与日志使用。"""
    return _resolve_categories(search_type)


def normalize_search_type(search_type: str | None) -> str:
    """返回用于查权重的分类：resolve_category 结果；无文件时返回传入值或第一个分类。"""
    st = (search_type or "").strip()
    if not st:
        cats = get_categories()
        return cats[0] if cats else ""
    return resolve_category(st)


def _resolve_categories(search_type: Union[str, List[str]]) -> List[str]:
    """将 search_type（单分类或多分类）解析为分类名列表。"""
    if isinstance(search_type, list):
        return [resolve_category(str(s).strip()) for s in search_type if str(s).strip()]
    return [resolve_category(str(search_type).strip())] if str(search_type).strip() else []


def _normalize_category_weights(categories: List[str], category_weights: Optional[Dict[str, float]]) -> Dict[str, float]:
    """多分类时各分类的权重：若未提供则等权；提供则取子集并归一化。"""
    if not categories:
        return {}
    if not category_weights:
        w = 1.0 / len(categories)
        return {c: w for c in categories}
    subset = {c: float(category_weights[c]) for c in categories if c in category_weights and float(category_weights[c]) > 0}
    if not subset:
        return {c: 1.0 / len(categories) for c in categories}
    total = sum(subset.values())
    return {c: subset[c] / total for c in subset}


def get_search_type_engines(search_type: Union[str, List[str]]) -> List[str]:
    """参与检索的引擎列表：单分类取该分类；多分类取各分类引擎的并集（保序：按首次出现顺序）。"""
    categories = _resolve_categories(search_type)
    if not categories:
        return list(DEFAULT_ENGINES)
    if len(categories) == 1:
        by_cat = _by_category()
        data = by_cat.get(categories[0]) if by_cat else None
        if not data:
            return list(DEFAULT_ENGINES)
        ranked = data.get("ranked_engines")
        if ranked:
            return list(ranked)
        w = data.get("weights", {})
        return list(w.keys()) if w else list(DEFAULT_ENGINES)
    seen: set = set()
    out: List[str] = []
    by_cat = _by_category()
    for cat in categories:
        data = by_cat.get(cat) if by_cat else None
        engines = list(DEFAULT_ENGINES)
        if data:
            ranked = data.get("ranked_engines")
            engines = list(ranked) if ranked else list(data.get("weights", {}).keys()) or list(DEFAULT_ENGINES)
        for e in engines:
            if e not in seen:
                seen.add(e)
                out.append(e)
    return out if out else list(DEFAULT_ENGINES)


def get_search_type_engine_weights(
    search_type: Union[str, List[str]],
    category_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """引擎权重：单分类直接取该分类；多分类按分类权重加权平均（进阶版）。未提供 category_weights 时多分类等权。"""
    categories = _resolve_categories(search_type)
    if not categories:
        return {e: 1.0 for e in DEFAULT_ENGINES}
    if len(categories) == 1:
        by_cat = _by_category()
        data = by_cat.get(categories[0]) if by_cat else None
        if not data:
            return {e: 1.0 for e in DEFAULT_ENGINES}
        w = data.get("weights", {})
        return dict(w) if w else {e: 1.0 for e in DEFAULT_ENGINES}
    cw = _normalize_category_weights(categories, category_weights)
    by_cat = _by_category()
    merged: Dict[str, float] = {}
    for cat in categories:
        data = by_cat.get(cat) if by_cat else None
        w = (data.get("weights", {}) if data else {}) or {e: 1.0 for e in DEFAULT_ENGINES}
        for engine, val in w.items():
            merged[engine] = merged.get(engine, 0.0) + float(val) * cw.get(cat, 0.0)
    if not merged:
        return {e: 1.0 for e in DEFAULT_ENGINES}
    total = sum(merged.values())
    if total <= 0:
        return {e: 1.0 / len(merged) for e in merged}
    return {e: round(merged[e] / total, 6) for e in merged}


def get_domain_weights_for_search_type(
    search_type: Union[str, List[str]],
    category_weights: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, float]]:
    """域名权重：单分类取该分类；多分类按分类权重加权平均（进阶版）。"""
    _ensure_weights_loaded()
    if not _DOMAIN_WEIGHTS_BY_CATEGORY:
        return None
    categories = _resolve_categories(search_type)
    if not categories:
        return None
    if len(categories) == 1:
        w = (_DOMAIN_WEIGHTS_BY_CATEGORY.get(categories[0]) or {}).get("weights", {})
        return dict(w) if w else None
    cw = _normalize_category_weights(categories, category_weights)
    merged: Dict[str, float] = {}
    for cat in categories:
        w = (_DOMAIN_WEIGHTS_BY_CATEGORY.get(cat) or {}).get("weights", {}) or {}
        for domain, val in w.items():
            merged[domain] = merged.get(domain, 0.0) + float(val) * cw.get(cat, 0.0)
    return dict(merged) if merged else None


def get_rerank_weights() -> Dict[str, float]:
    """融合权重，仅来自 rerank_policy.json。无文件时返回等权兜底。"""
    _ensure_weights_loaded()
    if _RERANK_POLICY:
        fusion = (_RERANK_POLICY.get("fusion_score") or {}).get("weights", {})
        if fusion:
            return {
                "rrf": float(fusion.get("w_rrf", 0.33)),
                "engine": float(fusion.get("w_engine", 0.33)),
                "domain": float(fusion.get("w_domain", 0.34)),
            }
    return {"rrf": 0.33, "engine": 0.33, "domain": 0.34}


def get_rrf_k() -> int:
    """RRF 的 k，仅来自 rerank_policy.json。无文件时返回 60。"""
    _ensure_weights_loaded()
    if _RERANK_POLICY:
        k = (_RERANK_POLICY.get("fusion_score") or {}).get("rrf_k")
        if k is not None:
            return int(k)
    return 60


def get_aggregate_engines() -> List[str]:
    """参与聚合的引擎列表：reference/aggregate_engines.txt（每行一个） > 环境变量 AGGREGATE_ENGINES > 默认 baidu,tavily,zhipu。"""
    skill_root = Path(__file__).resolve().parent.parent
    engines_file = skill_root / "reference" / "aggregate_engines.txt"
    if engines_file.exists():
        with open(engines_file, "r", encoding="utf-8") as f:
            lines = [x.strip() for x in f.readlines() if x.strip()]
        if lines:
            return lines
    raw = os.environ.get(ENV_AGGREGATE_ENGINES, "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return list(DEFAULT_ENGINES)


def resolve_enabled_engines(search_type: Union[str, List[str]]) -> List[str]:
    """推荐引擎（单分类或多分类并集）与 AGGREGATE_ENGINES 的交集，保序。"""
    preferred = get_search_type_engines(search_type)
    enabled = get_aggregate_engines()
    enabled_set = set(enabled)
    resolved = [e for e in preferred if e in enabled_set]
    return resolved or enabled


def get_log_path() -> str:
    return os.environ.get(ENV_AGGREGATE_LOG_PATH, DEFAULT_LOG_PATH).strip() or DEFAULT_LOG_PATH


def get_timing_debug() -> bool:
    v = os.environ.get(ENV_AGGREGATE_TIMING, "").strip().lower()
    return v in ("1", "true", "yes", "on")


def get_baidu_api_key() -> str:
    return (os.environ.get(ENV_BAIDU_APPBUILDER_API_KEY) or "bce-v3/ALTAK-tidMPgbDzQgUy0jij6huN/359701cd4e7eecaa8c3d0e80c86259ee1a79dd4a").strip()


def get_tavily_api_key() -> str:
    return (os.environ.get(ENV_TAVILY_API_KEY) or "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").strip()


def get_zhipu_api_key() -> str:
    return (os.environ.get(ENV_ZHIPU_API_KEY) or "0944e4fd59d14bf79e0aeffadcdb9fc5.vsRaHfsUjme7S9bw").strip()
