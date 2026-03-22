"""
Pipeline:
1) 去重（同 URL 多源合并）
2) 空白/乱码清洗 + 单条截断
3) BM25 过滤 + RRF/引擎/域名加权重排
4) 按 token 保底 + 总长度限制
5) Top-K 输出
"""

from __future__ import annotations

import json
import re
from typing import List, Union
from urllib.parse import urlparse

from features.bm25_ngram import score_documents_with_bm25_ngrams
from features.dedupe import dedupe_by_url
import config as _config

SPAM_MARKERS = [
    "download brochure", "enroll now", "whatsapp us", "course overview",
    "career support", "get certified", "join our bootcamp", "limited seats",
    "free demo", "register now", "立即报名", "免费试听", "领取课程",
    "限时优惠", "咨询客服", "点击下载", "预约课程",
]

DOMAIN_PRIORITY_PREFER = [
    ("github.com", 25), ("arxiv.org", 22), ("huggingface.co", 20), ("docs.", 18),
    ("developer.", 15), ("developers.", 15), ("learn.microsoft.com", 14),
    ("developers.google.com", 14), ("pytorch.org", 12), ("tensorflow.org", 12),
]
DOMAIN_PRIORITY_PENALTY = [("reddit.com", -5), ("quora.com", -5)]
_LENGTH_FIELDS = ("title", "url", "content", "date")


def _domain_from_url(url: str) -> str | None:
    if not url or not url.strip():
        return None
    try:
        p = urlparse(url.strip())
        return (p.hostname or "").lower() or None
    except Exception:
        return None


def _domain_for_weight_lookup(url: str) -> str:
    """与权重文件中域名格式一致：小写、去掉 www 前缀。"""
    d = _domain_from_url(url)
    if not d:
        return ""
    return d[4:] if d.startswith("www.") else d


def _domain_priority(url: str) -> int:
    u = (url or "").lower()
    for needle, score in DOMAIN_PRIORITY_PREFER:
        if needle in u:
            return score
    for needle, score in DOMAIN_PRIORITY_PENALTY:
        if needle in u:
            return score
    return 0


def _tokenize(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    s = (text or "").strip().lower()
    tokens = re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+", s)
    out: list[str] = []
    for token in tokens:
        if re.match(r"^[\u4e00-\u9fff]+$", token):
            if len(token) > 1:
                out.append(token)
        elif len(token) >= 2:
            out.append(token)
    return out


def _keyword_tokens_from_group(keywords: list[str] | None) -> list[str]:
    if not keywords:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for kw in keywords:
        for t in _tokenize(str(kw or "").strip()):
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


def _is_garbled(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return True
    if s.count("\ufffd") >= 2:
        return True
    valid_chars = re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]", s)
    return len(valid_chars) / max(len(s), 1) < 0.08


def _is_spammy(item: dict) -> bool:
    title = (item.get("title") or "").lower()
    content = (item.get("content") or "").lower()
    url = (item.get("url") or "").lower()
    return any(m in title or m in content or m in url for m in SPAM_MARKERS)


def _item_for_length(item: dict) -> dict:
    return {k: item.get(k) for k in _LENGTH_FIELDS}


def serialize_results_for_length(items: list[dict]) -> str:
    reduced = [_item_for_length(i) for i in items]
    return json.dumps(reduced, ensure_ascii=False, separators=(",", ":"))


def _item_serialized_length(item: dict) -> int:
    return len(json.dumps(_item_for_length(item), ensure_ascii=False, separators=(",", ":")))


def _truncate_item_to_chars(item: dict, *, per_item_max_chars: int) -> dict:
    if per_item_max_chars <= 0:
        return item
    row = dict(item)
    if _item_serialized_length(row) <= per_item_max_chars:
        return row
    content = (row.get("content") or "").strip()
    title = (row.get("title") or "").strip()
    shrink_target = max(40, per_item_max_chars // 2)
    if len(content) > shrink_target:
        row["content"] = content[:shrink_target] + "..."
    if len(title) > max(20, per_item_max_chars // 5):
        row["title"] = title[: max(20, per_item_max_chars // 5)] + "..."
    if _item_serialized_length(row) > per_item_max_chars:
        row["content"] = (row.get("content") or "")[: max(10, per_item_max_chars // 3)]
    return row


def clean_items(items: list[dict], *, per_item_max_chars: int) -> list[dict]:
    out: list[dict] = []
    for item in items:
        title = (item.get("title") or "").strip()
        content = (item.get("content") or "").strip()
        url = (item.get("url") or "").strip()
        if not url:
            continue
        if not title and not content:
            continue
        if _is_spammy(item):
            continue
        # 只要标题或正文其中之一可读即可
        if _is_garbled(title) and _is_garbled(content):
            continue
        out.append(_truncate_item_to_chars(item, per_item_max_chars=per_item_max_chars))
    return out


def bm25_prefilter(items: list[dict], keywords: list[str] | None) -> list[dict]:
    query_tokens = _keyword_tokens_from_group(keywords)
    if not items or not query_tokens:
        return items
    docs = [f"{it.get('title', '')} {it.get('content', '')}".strip() for it in items]
    scores = score_documents_with_bm25_ngrams(docs, query_tokens, ngram_n=2)
    if not scores:
        return items
    indexed = list(enumerate(scores))
    indexed.sort(key=lambda x: x[1], reverse=True)
    keep_top = set(i for i, _ in indexed[: _config.get_bm25_min_keep()])
    out: list[dict] = []
    for i, item in enumerate(items):
        s = float(scores[i])
        if s >= _config.get_bm25_min_score() or i in keep_top:
            row = dict(item)
            row["bm25_score"] = round(s, 6)
            out.append(row)
    return out


def _normalize(vals: list[float]) -> list[float]:
    if not vals:
        return []
    lo = min(vals)
    hi = max(vals)
    if hi - lo < 1e-9:
        return [1.0 if hi > 0 else 0.0 for _ in vals]
    return [(v - lo) / (hi - lo) for v in vals]


def _rrf_score(item: dict, rrf_k_override: int | None = None) -> float:
    k = int(rrf_k_override) if rrf_k_override is not None else _config.get_rrf_k()
    total = 0.0
    for sr in item.get("stream_ranks", []) or []:
        rank = int(sr.get("rank", 0) or 0)
        if rank > 0:
            total += 1.0 / (k + rank)
    return total


def _engine_weight_score(item: dict, engine_weights: dict[str, float]) -> float:
    srcs = [str(s).strip() for s in (item.get("sources") or []) if str(s).strip()]
    if not srcs:
        return 0.0
    vals = [float(engine_weights.get(s, 1.0)) for s in srcs]
    return sum(vals) / len(vals)


def _domain_weight_score(
    item: dict,
    search_type: Union[str, List[str]],
    domain_weights_map: dict[str, float] | None = None,
) -> float:
    """域名得分仅来自权重文件；无文件时返回中性 1.0，不在代码中配置。"""
    if domain_weights_map is not None:
        domain = _domain_for_weight_lookup(item.get("url") or "")
        if domain:
            return float(domain_weights_map.get(domain, 0.0))
        return 0.0
    return 1.0


def sort_by_relevance(
    items: list[dict],
    keywords: list[str] | None,
    *,
    search_type: Union[str, List[str]] = "general",
    engine_weights: dict[str, float] | None = None,
    domain_weights_map: dict[str, float] | None = None,
    threshold: float | None = None,
    rerank_weights_override: dict | None = None,
    bm25_fusion_weight: float | None = None,
    rrf_k_override: int | None = None,
    single_engine: bool = False,
) -> list[dict]:
    if not items:
        return items
    filtered_items: list[dict] = []
    for it in items:
        if _is_spammy(it):
            continue
        title = (it.get("title") or "").strip()
        content = (it.get("content") or "").strip()
        if _is_garbled(title) and _is_garbled(content):
            continue
        filtered_items.append(it)
    items = filtered_items
    if not items:
        return []
    ew = engine_weights or _config.get_search_type_engine_weights(search_type)
    rrf_raw = [_rrf_score(it, rrf_k_override) for it in items]
    eng_raw = [_engine_weight_score(it, ew) for it in items]
    dom_raw = [_domain_weight_score(it, search_type, domain_weights_map) for it in items]
    bm25_raw = [float(it.get("bm25_score", 0.0) or 0.0) for it in items]

    rrf_norm = _normalize(rrf_raw)
    eng_norm = _normalize(eng_raw)
    dom_norm = _normalize(dom_raw)
    bm25_norm = _normalize(bm25_raw)

    rerank = _config.get_rerank_weights()
    if rerank_weights_override:
        w_rrf = float(rerank_weights_override.get("rrf", rerank.get("rrf", 0.55)))
        w_engine = float(rerank_weights_override.get("engine", rerank.get("engine", 0.30)))
        w_domain = float(rerank_weights_override.get("domain", rerank.get("domain", 0.15)))
    else:
        w_rrf = float(rerank.get("rrf", 0.55))
        w_engine = float(rerank.get("engine", 0.30))
        w_domain = float(rerank.get("domain", 0.15))
    w_bm25 = 0.15 if bm25_fusion_weight is None else float(bm25_fusion_weight)
    if single_engine:
        w_engine = 0.0
        total_base = w_rrf + w_domain
        if total_base < 1e-9:
            w_rrf, w_domain = 0.5 * (1.0 - w_bm25), 0.5 * (1.0 - w_bm25)
        else:
            w_rrf = (w_rrf / total_base) * (1.0 - w_bm25)
            w_domain = (w_domain / total_base) * (1.0 - w_bm25)
    else:
        w_base = 1.0 - w_bm25

    scored: list[tuple[dict, float]] = []
    for i, item in enumerate(items):
        if single_engine:
            base = (w_rrf * rrf_norm[i]) + (w_domain * dom_norm[i])
            final_score = base + (w_bm25 * bm25_norm[i])
        else:
            base = (w_rrf * rrf_norm[i]) + (w_engine * eng_norm[i]) + (w_domain * dom_norm[i])
            final_score = (w_base * base) + (w_bm25 * bm25_norm[i])
        if threshold is not None and final_score < threshold:
            continue
        row = dict(item)
        row["score"] = round(final_score, 6)
        row["rrf_score"] = round(rrf_raw[i], 6)
        row["engine_score"] = round(eng_raw[i], 6)
        row["domain_score"] = round(dom_raw[i], 6)
        scored.append((row, final_score))

    scored.sort(key=lambda x: (-x[1], -_domain_priority((x[0].get("url") or ""))))
    return [x[0] for x in scored]


def _slim_result_item(item: dict) -> dict:
    """单条结果仅保留 title, content, url, date（发布时间），供对外输出。"""
    return {
        "title": (item.get("title") or "").strip(),
        "content": (item.get("content") or "").strip(),
        "url": (item.get("url") or "").strip(),
        "date": (item.get("date") or "").strip(),
    }


def _pairs_from_item(item: dict) -> set[tuple[str, str]]:
    kws = item.get("search_keywords") or []
    srcs = item.get("sources") or []
    out: set[tuple[str, str]] = set()
    for kw in kws:
        if not (kw and str(kw).strip()):
            continue
        for src in srcs:
            if not (src and str(src).strip()):
                continue
            out.add((str(kw).strip(), str(src).strip()))
    return out


def _coverage_per_pair(items: list[dict]) -> dict[tuple[str, str], list[int]]:
    pair_to_indices: dict[tuple[str, str], list[int]] = {}
    for idx, item in enumerate(items):
        for p in _pairs_from_item(item):
            pair_to_indices.setdefault(p, []).append(idx)
    return pair_to_indices


def _is_removable(idx: int, pair_to_indices: dict[tuple[str, str], list[int]], item_pairs: set[tuple[str, str]]) -> bool:
    for p in item_pairs:
        indices = pair_to_indices.get(p, [])
        others = [i for i in indices if i != idx]
        if not others:
            return False
    return True


def cap_total_length(items: list[dict], max_total_chars: int, *, preserve_per_keyword_source: bool = True) -> list[dict]:
    if max_total_chars <= 0:
        return items
    total_len = len(serialize_results_for_length(items))
    if total_len <= max_total_chars:
        return items
    indexed = list(enumerate(items))
    pair_to_indices = _coverage_per_pair(items) if preserve_per_keyword_source else {}
    indexed.sort(key=lambda x: float(x[1].get("score", 0.0)))
    kept_indices: set[int] = set(range(len(items)))
    for idx, item in indexed:
        if len(serialize_results_for_length([items[i] for i in sorted(kept_indices)])) <= max_total_chars:
            break
        if idx not in kept_indices:
            continue
        item_pairs = _pairs_from_item(item)
        if preserve_per_keyword_source and not _is_removable(idx, pair_to_indices, item_pairs):
            continue
        kept_indices.discard(idx)
        if preserve_per_keyword_source:
            for p in item_pairs:
                pair_to_indices[p] = [i for i in pair_to_indices.get(p, []) if i != idx]
    return [items[i] for i in range(len(items)) if i in kept_indices]


def filter_and_keep_per_keyword(items: list[dict], *, max_items: int | None = None) -> list[dict]:
    kept: list[dict] = []
    used_urls: set[str] = set()
    covered_pairs: set[tuple[str, str]] = set()
    # 第一轮：先满足覆盖
    for item in items:
        url = (item.get("url") or "").strip()
        if not url or url in used_urls:
            continue
        item_pairs = _pairs_from_item(item)
        if item_pairs and (item_pairs - covered_pairs):
            covered_pairs |= item_pairs
            used_urls.add(url)
            kept.append(item)
    # 第二轮：补齐余项（保持当前分数顺序）
    for item in items:
        url = (item.get("url") or "").strip()
        if not url or url in used_urls:
            continue
        if not (item.get("title") or item.get("url")):
            continue
        used_urls.add(url)
        kept.append(item)
    return kept[:max_items] if (max_items is not None and max_items > 0) else kept


def run_pipeline(
    items: list[dict],
    query: str,
    *,
    keywords: list[str] | None = None,
    search_type: Union[str, List[str]] = "general",
    engine_weights: dict[str, float] | None = None,
    max_items: int = 20,
    relevance_threshold: float | None = None,
    max_total_chars: int | None = None,
    single_engine: bool = False,
) -> list[dict]:
    """
    去重、清洗、BM25、融合排序、长度与 top-k 截断。
    relevance_threshold: 若传入则过滤掉融合分低于该值的结果（当前 CLI 未使用）。
    """
    # 1) 去重，同 URL 多源合并
    items = dedupe_by_url(items)
    if not items:
        return []

    # 2) 空白/乱码删除 + 单条截断
    per_item_max = _config.PER_ITEM_MAX_CHARS_CAP
    if max_total_chars is not None and max_total_chars > 0:
        per_item_max = min(max_total_chars // 4, _config.PER_ITEM_MAX_CHARS_CAP)
    items = clean_items(items, per_item_max_chars=per_item_max)
    if not items:
        return []

    # 3) BM25 过滤 + 多指标加权重排（单源时不用引擎权重，仅 RRF + 域名 + BM25）
    items = bm25_prefilter(items, keywords or ([query] if query else []))
    domain_weights_map = _config.get_domain_weights_for_search_type(search_type)
    items = sort_by_relevance(
        items,
        keywords or ([query] if query else []),
        search_type=search_type,
        engine_weights=engine_weights,
        domain_weights_map=domain_weights_map,
        threshold=relevance_threshold,
        single_engine=single_engine,
    )
    if not items:
        return []

    # 4) token 保底筛选（不先截断 top-k）
    items = filter_and_keep_per_keyword(items, max_items=None)

    # 6) token 长度限定 + 保底（沿用 cap）
    if max_total_chars is not None and max_total_chars > 0:
        items = cap_total_length(items, max_total_chars, preserve_per_keyword_source=True)

    # 7) top k
    if max_items > 0:
        items = items[:max_items]

    return items
