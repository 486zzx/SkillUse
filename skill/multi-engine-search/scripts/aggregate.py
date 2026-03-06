"""
主流程：支持「用户问题 + 关键词组」两参数；关键词组与多引擎并行搜索 → 合并 → pipeline → 统一输出。
无关键词组时退化为单查询（可选改写）；有关键词组时对每个关键词×每个引擎并行请求。
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from fetchers import get_fetchers
from pipeline import run_pipeline
from query_rewriter import rewrite_query

# 打桩：设 AGGREGATE_TIMING=1 时向 stderr 输出各阶段耗时，便于定位慢点
_DEBUG_TIMING = os.environ.get("AGGREGATE_TIMING", "").strip().lower() in ("1", "true", "yes", "on")


def _log_timing(msg: str) -> None:
    if _DEBUG_TIMING:
        print(f"[aggregate] {msg}", file=sys.stderr, flush=True)


def _query_rewrite_enabled() -> bool:
    """是否启用查询改写。默认 True；设 AGGREGATE_QUERY_REWRITE=0 或 false 关闭。"""
    v = os.environ.get("AGGREGATE_QUERY_REWRITE", "").strip().lower()
    if not v:
        return True
    return v not in ("0", "false", "no", "off", "disabled")


def aggregate(
    query: str,
    *,
    keywords: list[str] | None = None,
    max_items: int = 50,
    use_rewrite: bool | None = None,
) -> dict[str, Any]:
    """
    并行请求：若提供 keywords 则对每个 (关键词 × 引擎) 并行搜索；否则对单查询多引擎并行。
    query 为用户问题，用于改写建议与 pipeline 相关度/保底；实际请求用 keywords 各元素或改写后的 query。
    """
    query = (query or "").strip()
    if not query and not (keywords and any(k and str(k).strip() for k in keywords)):
        return {
            "success": False,
            "results": [],
            "total_count": 0,
            "sources_used": [],
            "error": "未提供 query 或有效 keywords",
            "query_rewrite": None,
            "stats": {
                "total_original": 0,
                "total_after_dedup": 0,
                "dedup_rate": 0.0,
                "engine_counts": {},
                "duration_ms": 0,
            },
        }
    if not query and keywords:
        query = (keywords[0] or "").strip() or ""

    t0 = time.perf_counter()
    use_rewrite = use_rewrite if use_rewrite is not None else _query_rewrite_enabled()
    rewrite_result = rewrite_query(query)
    t_rewrite = time.perf_counter()
    _log_timing(f"rewrite_query: {round((t_rewrite - t0) * 1000)} ms")

    # 实际参与搜索的查询列表：有关键词组则用关键词组（不改写）；否则用单条（可改写）
    if keywords and len(keywords) > 0:
        search_queries = [str(k).strip() for k in keywords if str(k).strip()]
        if not search_queries:
            search_queries = [rewrite_result["best_query"] if use_rewrite else query]
    else:
        search_queries = [rewrite_result["best_query"] if use_rewrite else query]

    fetchers = get_fetchers()
    t_fetchers = time.perf_counter()
    _log_timing(f"get_fetchers: {round((t_fetchers - t_rewrite) * 1000)} ms, engines={len(fetchers)}")

    sources_used: list[str] = []
    engine_counts: dict[str, int] = {}
    all_items: list[dict] = []
    errors: list[str] = []

    if not fetchers:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        return {
            "success": False,
            "results": [],
            "total_count": 0,
            "sources_used": [],
            "error": "未启用任何搜索引擎（可设置 AGGREGATE_ENGINES 或注册 Fetcher）",
            "query_rewrite": {
                "original": query,
                "best_query": search_queries[0] if search_queries else query,
                "keywords": search_queries,
                "suggestions": rewrite_result.get("suggestions", []),
                "is_developer_query": rewrite_result.get("is_developer_query", False),
            },
            "stats": {
                "total_original": 0,
                "total_after_dedup": 0,
                "dedup_rate": 0.0,
                "engine_counts": {},
                "duration_ms": duration_ms,
            },
        }

    # 并行：每个 (关键词 × 引擎) 一个任务；各引擎用自身默认的 max_results、timeout
    def do_fetch(f: Any, q: str) -> tuple[str, str, list[dict], str]:
        t_start = time.perf_counter()
        source_id, items, err = f.fetch(q)
        elapsed_ms = round((time.perf_counter() - t_start) * 1000)
        _log_timing(f"fetch {source_id} {q[:40]!r}... {elapsed_ms} ms, items={len(items)}, err={bool(err)}")
        return (source_id, q, items, err)

    tasks = [(f, q) for q in search_queries for f in fetchers]
    _log_timing(f"submit {len(tasks)} tasks (keywords={len(search_queries)}, engines={len(fetchers)}), max_workers={max(1, len(tasks))}")
    t_fetch_start = time.perf_counter()

    # 线程数 = 任务数（关键词×引擎），保证全部并发且不超额，同机多调用时不拥塞
    max_workers = max(1, len(tasks))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(do_fetch, f, q) for f, q in tasks]
        for fut in as_completed(futures):
            try:
                source_id, search_q, items, err = fut.result()
                if err:
                    errors.append(f"{source_id}({search_q!r}): {err}")
                else:
                    if source_id not in sources_used:
                        sources_used.append(source_id)
                    engine_counts[source_id] = engine_counts.get(source_id, 0) + len(items)
                    for it in items:
                        it["search_keyword"] = search_q
                    all_items.extend(items)
            except Exception as e:
                errors.append(str(e))

    t_fetch_end = time.perf_counter()
    _log_timing(f"all fetches done (wall): {round((t_fetch_end - t_fetch_start) * 1000)} ms, total_items={len(all_items)}")

    if not all_items:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        return {
            "success": False,
            "results": [],
            "total_count": 0,
            "sources_used": sources_used,
            "error": "; ".join(errors) if errors else "无有效结果",
            "query_rewrite": {
                "original": query,
                "best_query": search_queries[0] if search_queries else query,
                "keywords": search_queries,
                "suggestions": rewrite_result.get("suggestions", []),
                "is_developer_query": rewrite_result.get("is_developer_query", False),
            },
            "stats": {
                "total_original": 0,
                "total_after_dedup": 0,
                "dedup_rate": 0.0,
                "engine_counts": engine_counts,
                "duration_ms": duration_ms,
            },
        }

    total_original = len(all_items)
    t_pipeline_start = time.perf_counter()
    # 排序阶段使用“关键词组”做分词相关度（而非用户原始问句 query）
    all_items = run_pipeline(all_items, query, keywords=search_queries, max_items=max_items)
    t_pipeline_end = time.perf_counter()
    _log_timing(f"run_pipeline: {round((t_pipeline_end - t_pipeline_start) * 1000)} ms, in={total_original} out={len(all_items)}")

    total_after_dedup = len(all_items)
    dedup_rate = round((1 - total_after_dedup / total_original) * 100, 1) if total_original else 0.0
    duration_ms = round((time.perf_counter() - t0) * 1000)
    _log_timing(f"total: {duration_ms} ms")

    # 给每条结果加 1-based 序号
    results_with_index = []
    for i, item in enumerate(all_items):
        row = dict(item)
        row["aggregate_index"] = i + 1
        results_with_index.append(row)

    return {
        "success": True,
        "results": results_with_index,
        "total_count": len(results_with_index),
        "sources_used": sources_used,
        "error": "; ".join(errors) if errors else "",
        "query_rewrite": {
            "original": query,
            "best_query": search_queries[0] if search_queries else query,
            "keywords": search_queries,
            "suggestions": rewrite_result.get("suggestions", []),
            "is_developer_query": rewrite_result.get("is_developer_query", False),
        },
        "stats": {
            "total_original": total_original,
            "total_after_dedup": total_after_dedup,
            "dedup_rate": dedup_rate,
            "engine_counts": engine_counts,
            "duration_ms": duration_ms,
        },
    }
