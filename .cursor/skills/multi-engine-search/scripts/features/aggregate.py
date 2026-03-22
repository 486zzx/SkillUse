"""
主流程：仅接收关键词组 + 搜索类型。
按搜索类型选引擎并并发搜索，随后执行去重/清洗/BM25/RRF 多指标重排等后处理。
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from features.fetchers.base import get_fetchers
from features.pipeline import run_pipeline, _slim_result_item

SCRIPT_DIR = Path(__file__).resolve().parent.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from skill_logging._log import init_logger, log_event, trace_call

import config as _config

init_logger("aggregate_search")


@trace_call
async def aggregate(
    *,
    keywords: list[str],
    client: Any,
    search_type: str | list[str] = _config.DEFAULT_SEARCH_TYPE,
    search_mode: str = _config.DEFAULT_SEARCH_MODE,
) -> dict[str, Any]:
    """
    仅接收关键词组 + 搜索类型 + 搜索模式。对每个 (关键词 × 引擎) 并行搜索，合并后走 pipeline 输出。
    category_weights、max_items、max_total_chars 由 config 指定。
    search_type 可为单分类（str）或多分类（list[str]）；多分类时按 config.DEFAULT_CATEGORY_WEIGHTS 或等权合并。
    search_mode 为 Fast/Balanced/Precision 之一，决定参与引擎列表；单源时排序仅用 RRF+域名+BM25。
    client: HTTP 客户端实例（如 RequestsHttpClient），须由 CLI 或调用方传入，勿使用全局单例。
    """
    keywords = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    categories = _config.get_resolved_categories(search_type)
    category_weights = _config.DEFAULT_CATEGORY_WEIGHTS
    max_items = _config.DEFAULT_MAX_ITEMS
    max_total_chars = _config.DEFAULT_MAX_TOTAL_CHARS
    mode = (search_mode or "").strip() or _config.DEFAULT_SEARCH_MODE
    if mode not in _config.VALID_SEARCH_MODES:
        mode = _config.DEFAULT_SEARCH_MODE

    if not keywords:
        return {"success": False, "results": [], "total_count": 0, "error": "未提供有效 keywords"}

    original_str = " ".join(keywords)
    t0 = time.perf_counter()
    search_queries = list(keywords)

    selected_engines = _config.resolve_enabled_engines(search_type, mode)
    _config.set_current_engines(selected_engines)
    engine_weights = _config.get_search_type_engine_weights(search_type, category_weights)
    single_engine = len(selected_engines) == 1
    fetchers = get_fetchers(engine_ids=selected_engines)
    sources_used: list[str] = []
    engine_counts: dict[str, int] = {}
    all_items: list[dict] = []
    errors: list[str] = []

    if not fetchers:
        return {"success": False, "results": [], "total_count": 0, "error": "未启用任何搜索引擎（可设置 AGGREGATE_ENGINES 或注册 Fetcher）"}

    # 并行：每个 (关键词 × 引擎) 一个任务；整体墙钟超时按搜索模式从 search_modes.json 读取，到点后未返回的请求不再等待
    fetch_timeout_s = _config.get_fetch_timeout_for_search_mode(mode)
    tasks = [(f, q) for q in search_queries for f in fetchers]

    async def do_fetch(f: Any, q: str) -> tuple[str, str, list[dict], str] | BaseException:
        fname = getattr(f, "engine_id", type(f).__name__)
        try:
            log_event(
                "aggregate",
                "api_request",
                input={"method": "FETCH", "engine": fname, "query": q, "timeout_s": fetch_timeout_s},
                request_body="",
                output_summary={},
                latency_ms=None,
                success=None,
                error="",
            )
            t_f = time.perf_counter()
            source_id, items, err = await asyncio.wait_for(
                f.fetch(q, timeout=fetch_timeout_s, client=client),
                timeout=fetch_timeout_s + 1,
            )
            elapsed_f = (time.perf_counter() - t_f) * 1000
            fetch_ok = not bool(err)
            log_event(
                "aggregate",
                "api_response",
                level="INFO" if fetch_ok else "ERROR",
                input={"method": "FETCH", "engine": fname, "query": q, "timeout_s": fetch_timeout_s},
                output_summary={"success": fetch_ok, "items": len(items), "engine": source_id},
                response_body={"source_id": source_id, "items": items, "error": err},
                latency_ms=elapsed_f,
                success=fetch_ok,
                error="" if fetch_ok else str(err),
            )
            return (source_id, q, items, err)
        except asyncio.TimeoutError:
            return asyncio.TimeoutError()
        except Exception as e:
            return e

    results = await asyncio.gather(*[do_fetch(f, q) for f, q in tasks], return_exceptions=False)
    for res in results:
        if isinstance(res, BaseException):
            errors.append("(整体超时，未返回的请求已放弃)" if isinstance(res, asyncio.TimeoutError) else str(res))
            continue
        source_id, search_q, items, err = res
        if err:
            errors.append(f"{source_id}({search_q!r}): {err}")
        else:
            if source_id not in sources_used:
                sources_used.append(source_id)
            engine_counts[source_id] = engine_counts.get(source_id, 0) + len(items)
            for idx, it in enumerate(items, start=1):
                it["search_keyword"] = search_q
                it["stream_rank"] = idx
            all_items.extend(items)

    if not all_items:
        return {"success": False, "results": [], "total_count": 0, "error": "; ".join(errors) if errors else "无有效结果"}

    total_original = len(all_items)
    # 排序阶段使用“关键词组”做分词相关度；单源时仅 RRF+域名+BM25，不用引擎权重
    all_items = run_pipeline(
        all_items,
        original_str,
        keywords=search_queries,
        search_type=search_type,
        engine_weights=engine_weights,
        max_items=max_items,
        max_total_chars=max_total_chars,
        single_engine=single_engine,
    )

    total_after_dedup = len(all_items)
    duration_ms = round((time.perf_counter() - t0) * 1000)

    # 给每条结果加 1-based 序号；对外仅返回 title/content/url/date，完整数据写日志
    results_with_index = []
    for i, item in enumerate(all_items):
        row = dict(item)
        row["aggregate_index"] = i + 1
        results_with_index.append(row)

    out_slim = {
        "success": True,
        "results": [_slim_result_item(r) for r in results_with_index],
        "total_count": len(results_with_index),
        "error": "; ".join(errors) if errors else "",
    }
    return out_slim
