"""
主流程：仅接收关键词组 + 搜索类型。
按搜索类型选引擎并并发搜索，随后执行去重/清洗/BM25/RRF 多指标重排等后处理。
"""

from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from fetchers import get_fetchers
from pipeline import run_pipeline

import config as _config

_AGGREGATE_LOG_LOCK = threading.Lock()


def _log_timing(msg: str) -> None:
    if _config.get_timing_debug():
        print(f"[aggregate] {msg}", file=sys.stderr, flush=True)


def _append_aggregate_log(
    *,
    query: str,
    keywords: list[str] | None,
    search_type: str,
    search_mode: str,
    output: dict[str, Any],
) -> None:
    """将本次调用的输入、输出追加到 JSONL 日志文件，保证留存；写入失败不影响主流程。"""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "input": {
            "query": query,
            "keywords": keywords,
            "search_type": search_type,
            "search_mode": search_mode,
        },
        "output": output,
    }
    try:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with _AGGREGATE_LOG_LOCK:
            with open(_config.get_log_path(), "a", encoding="utf-8") as f:
                f.write(line)
    except (OSError, TypeError) as e:
        print(f"[aggregate] log write failed: {e}", file=sys.stderr, flush=True)


def aggregate(
    *,
    keywords: list[str],
    search_type: str | list[str] = _config.DEFAULT_SEARCH_TYPE,
    search_mode: str = _config.DEFAULT_SEARCH_MODE,
) -> dict[str, Any]:
    """
    仅接收关键词组 + 搜索类型 + 搜索模式。对每个 (关键词 × 引擎) 并行搜索，合并后走 pipeline 输出。
    category_weights、max_items、max_total_chars 由 config 指定。
    search_type 可为单分类（str）或多分类（list[str]）；多分类时按 config.DEFAULT_CATEGORY_WEIGHTS 或等权合并。
    search_mode 为「快速」「思考」「专家」之一，默认快速，暂仅透传。
    """
    keywords = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    categories = _config.get_resolved_categories(search_type)
    search_type_display = categories[0] if len(categories) == 1 else ",".join(categories)
    category_weights = _config.DEFAULT_CATEGORY_WEIGHTS
    max_items = _config.DEFAULT_MAX_ITEMS
    max_total_chars = _config.DEFAULT_MAX_TOTAL_CHARS
    mode = (search_mode or "").strip() or _config.DEFAULT_SEARCH_MODE
    if mode not in _config.VALID_SEARCH_MODES:
        mode = _config.DEFAULT_SEARCH_MODE

    if not keywords:
        out = {
            "success": False,
            "results": [],
            "total_count": 0,
            "sources_used": [],
            "error": "未提供有效 keywords",
            "query_rewrite": None,
            "search_type": search_type_display,
            "search_mode": mode,
            "stats": {
                "total_original": 0,
                "total_after_dedup": 0,
                "dedup_rate": 0.0,
                "engine_counts": {},
                "duration_ms": 0,
            },
        }
        _append_aggregate_log(
            query="",
            keywords=keywords,
            search_type=search_type_display,
            search_mode=mode,
            output=out,
        )
        return out

    original_str = " ".join(keywords)
    t0 = time.perf_counter()
    search_queries = list(keywords)

    selected_engines = _config.resolve_enabled_engines(search_type)
    engine_weights = _config.get_search_type_engine_weights(search_type, category_weights)
    fetchers = get_fetchers(engine_ids=selected_engines)
    t_fetchers = time.perf_counter()
    _log_timing(
        f"get_fetchers: {round((t_fetchers - t0) * 1000)} ms, "
        f"search_type={search_type_display}, engines={len(fetchers)}"
    )

    sources_used: list[str] = []
    engine_counts: dict[str, int] = {}
    all_items: list[dict] = []
    errors: list[str] = []

    if not fetchers:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        out = {
            "success": False,
            "results": [],
            "total_count": 0,
            "sources_used": [],
            "error": "未启用任何搜索引擎（可设置 AGGREGATE_ENGINES 或注册 Fetcher）",
            "query_rewrite": {"keywords": search_queries},
            "search_type": search_type_display,
            "search_mode": mode,
            "selected_engines": selected_engines,
            "stats": {
                "total_original": 0,
                "total_after_dedup": 0,
                "dedup_rate": 0.0,
                "engine_counts": {},
                "duration_ms": duration_ms,
            },
        }
        _append_aggregate_log(
            query=original_str,
            keywords=keywords,
            search_type=search_type_display,
            search_mode=mode,
            output=out,
        )
        return out

    # 并行：每个 (关键词 × 引擎) 一个任务；显式传入 timeout 保证墙钟不超过设定值
    FETCH_TIMEOUT_S = 10
    def do_fetch(f: Any, q: str) -> tuple[str, str, list[dict], str]:
        t_start = time.perf_counter()
        source_id, items, err = f.fetch(q, timeout=FETCH_TIMEOUT_S)
        elapsed_ms = round((time.perf_counter() - t_start) * 1000)
        _log_timing(f"fetch {source_id} {q[:40]!r}... {elapsed_ms} ms, items={len(items)}, err={bool(err)}")
        return (source_id, q, items, err)

    tasks = [(f, q) for q in search_queries for f in fetchers]
    _log_timing(f"submit {len(tasks)} tasks (keywords={len(search_queries)}, engines={len(fetchers)}), max_workers={max(1, len(tasks))}")
    t_fetch_start = time.perf_counter()

    # 线程数 = 任务数（关键词×引擎），保证全部并发且不超额，同机多调用时不拥塞
    max_workers = max(1, len(tasks))
    # 墙钟上限：单任务若超过 FETCH_TIMEOUT_S+2 秒仍未返回则放弃，避免某引擎慢推送拉高整段耗时
    result_timeout_s = FETCH_TIMEOUT_S + 2
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(do_fetch, f, q) for f, q in tasks]
        for fut in as_completed(futures):
            try:
                source_id, search_q, items, err = fut.result(timeout=result_timeout_s)
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
            except FuturesTimeoutError:
                errors.append("(某任务超时，已放弃)")
            except Exception as e:
                errors.append(str(e))

    t_fetch_end = time.perf_counter()
    _log_timing(f"all fetches done (wall): {round((t_fetch_end - t_fetch_start) * 1000)} ms, total_items={len(all_items)}")

    if not all_items:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        out = {
            "success": False,
            "results": [],
            "total_count": 0,
            "sources_used": sources_used,
            "error": "; ".join(errors) if errors else "无有效结果",
            "query_rewrite": {"keywords": search_queries},
            "search_type": search_type_display,
            "search_mode": mode,
            "selected_engines": selected_engines,
            "stats": {
                "total_original": 0,
                "total_after_dedup": 0,
                "dedup_rate": 0.0,
                "engine_counts": engine_counts,
                "duration_ms": duration_ms,
            },
        }
        _append_aggregate_log(
            query=original_str,
            keywords=keywords,
            search_type=search_type_display,
            search_mode=mode,
            output=out,
        )
        return out

    total_original = len(all_items)
    t_pipeline_start = time.perf_counter()
    # 排序阶段使用“关键词组”做分词相关度；max_items、max_total_chars 来自 config
    all_items = run_pipeline(
        all_items,
        original_str,
        keywords=search_queries,
        search_type=search_type,
        engine_weights=engine_weights,
        max_items=max_items,
        max_total_chars=max_total_chars,
    )
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

    out = {
        "success": True,
        "results": results_with_index,
        "total_count": len(results_with_index),
        "sources_used": sources_used,
        "error": "; ".join(errors) if errors else "",
        "query_rewrite": {"keywords": search_queries},
        "search_type": search_type_display,
        "search_mode": mode,
        "selected_engines": selected_engines,
        "stats": {
            "total_original": total_original,
            "total_after_dedup": total_after_dedup,
            "dedup_rate": dedup_rate,
            "engine_counts": engine_counts,
            "duration_ms": duration_ms,
        },
    }
    _append_aggregate_log(
        query=original_str,
        keywords=keywords,
        search_type=search_type_display,
        search_mode=mode,
        output=out,
    )
    return out
