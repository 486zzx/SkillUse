"""
Pipeline：去重(含多源合并) → 重排序(Reranker + early boost + domain_weight) → 垃圾过滤 → 过滤与保底。
与 Cortex Scout 对齐：Reranker、关键词前置加分、域优先级、来源类型与 domain_weight、垃圾来源过滤。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from dedupe import dedupe_by_url

# 与 Cortex Scout rerank 一致：标题匹配权重 / 正文匹配权重
TITLE_WEIGHT = 0.4
CONTENT_WEIGHT = 0.2
# 关键词前置加分：摘要前 N 字内命中查询词时的乘数系数（Cortex: 0.2）
EARLY_BOOST_FACTOR = 0.2
EARLY_CONTENT_CHARS = 200

# 垃圾来源标记：英文（Cortex Scout）+ 中文场景
SPAM_MARKERS = [
    "download brochure",
    "enroll now",
    "whatsapp us",
    "course overview",
    "career support",
    "get certified",
    "join our bootcamp",
    "limited seats",
    "free demo",
    "register now",
    "立即报名",
    "免费试听",
    "领取课程",
    "限时优惠",
    "咨询客服",
    "点击下载",
    "预约课程",
]

# 域优先级：权威站加分、低质站减分（与 Cortex Scout domain_priority 一致）
DOMAIN_PRIORITY_PREFER = [
    ("github.com", 25),
    ("arxiv.org", 22),
    ("huggingface.co", 20),
    ("docs.", 18),
    ("developer.", 15),
    ("developers.", 15),
    ("learn.microsoft.com", 14),
    ("developers.google.com", 14),
    ("pytorch.org", 12),
    ("tensorflow.org", 12),
]
DOMAIN_PRIORITY_PENALTY = [("reddit.com", -5), ("quora.com", -5)]


def _domain_from_url(url: str) -> str | None:
    """从 URL 提取 host（域名）。"""
    if not url or not url.strip():
        return None
    try:
        p = urlparse(url.strip())
        return (p.hostname or "").lower() or None
    except Exception:
        return None


def _domain_priority(url: str) -> int:
    """域优先级分，用于同分 tie-breaker；越高越优先。"""
    u = (url or "").lower()
    for needle, score in DOMAIN_PRIORITY_PREFER:
        if needle in u:
            return score
    for needle, score in DOMAIN_PRIORITY_PENALTY:
        if needle in u:
            return score
    return 0


def _classify_source_type(url: str) -> tuple[str | None, str]:
    """按 URL 域名分类来源类型（与 Cortex Scout classify_search_result 一致）。返回 (domain, source_type)。"""
    domain = _domain_from_url(url)
    if not domain:
        return None, "other"
    d = domain.lower()
    if (
        d.endswith(".github.io")
        or "docs.rs" in d
        or "readthedocs" in d
        or "rust-lang.org" in d
        or "doc.rust-lang" in d
        or "developer.mozilla.org" in d
        or "learn.microsoft.com" in d
        or "man7.org" in d
        or "devdocs.io" in d
    ):
        return domain, "docs"
    if "github.com" in d or "gitlab.com" in d or "bitbucket.org" in d or "codeberg.org" in d:
        return domain, "repo"
    if (
        "news" in d
        or "blog" in d
        or "medium.com" in d
        or "dev.to" in d
        or "hackernews" in d
        or "reddit.com" in d
        or "thenewstack.io" in d
    ):
        return domain, "blog"
    if "youtube.com" in d or "vimeo.com" in d:
        return domain, "video"
    if "stackoverflow.com" in d or "stackexchange.com" in d:
        return domain, "qa"
    if "crates.io" in d or "npmjs.com" in d or "pypi.org" in d:
        return domain, "package"
    if "steam" in d or "facepunch" in d or "game" in d:
        return domain, "gaming"
    return domain, "other"


def _classify_query_topic(query: str) -> str:
    """查询主题：code / news / general；支持中英文（中文场景适配）。"""
    q = (query or "").lower()
    raw = query or ""
    code_needles_en = [
        "rust", "python", "javascript", "typescript", "golang",
        "error", "exception", "stack trace", "crate", "npm",
        "api", "sdk", "how to", "tutorial",
    ]
    code_needles_zh = ["教程", "文档", "错误", "异常", "接口", "安装", "代码", "如何", "怎么", "官网"]
    if any(n in q for n in code_needles_en) or any(n in raw for n in code_needles_zh):
        return "code"
    news_needles_en = ["news", "latest", "today", "breaking", "report", "2026", "2025"]
    news_needles_zh = ["新闻", "最新", "今日", "报道", "资讯"]
    if any(n in q for n in news_needles_en) or any(n in raw for n in news_needles_zh):
        return "news"
    return "general"


def _domain_weight(query: str, domain: str | None, source_type: str) -> float:
    """结合查询主题与来源类型的域权重 0.1~3.0（与 Cortex Scout domain_weight 完整版一致）。"""
    topic = _classify_query_topic(query)
    weight_map = {
        "repo": 1.40,
        "docs": 1.35,
        "qa": 1.25,
        "package": 1.20,
        "blog": 1.00,
        "video": 0.85,
        "gaming": 0.25,
    }
    weight = weight_map.get(source_type, 1.00)
    if not domain:
        return max(0.10, min(3.0, weight))
    d = domain.lower()
    if d.endswith(".gov") or d.endswith(".edu"):
        weight *= 1.50
    if d == "ietf.org" or d.endswith(".ietf.org"):
        weight *= 1.50
    if d == "w3.org" or d.endswith(".w3.org"):
        weight *= 1.50
    if d.endswith(".rust-lang.org") or d == "rust-lang.org":
        weight *= 1.35
    if "learn.microsoft.com" in d:
        weight *= 1.25
    if "wikipedia.org" in d:
        weight *= 1.30
    if topic == "code":
        if "github.com" in d or "stackoverflow.com" in d:
            weight *= 1.25
        if "docs.rs" in d:
            weight *= 1.30
    elif topic == "news":
        if "reuters.com" in d or "apnews.com" in d:
            weight *= 1.25
        if "bbc.co" in d or "bbc.com" in d:
            weight *= 1.10
    if "pinterest." in d or "facebook." in d or "tiktok." in d:
        weight *= 0.60
    if "medium.com" in d:
        weight *= 0.95
    if "doubleclick.net" in d or "googleadservices.com" in d or "googlesyndication.com" in d:
        weight *= 0.10
    return max(0.10, min(3.0, weight))


def _is_spammy(item: dict) -> bool:
    """标题/内容/URL 含营销/培训类短语则视为垃圾（中英文标记）。"""
    title = (item.get("title") or "").lower()
    content = (item.get("content") or "").lower()
    url = (item.get("url") or "").lower()
    return any(m in title or m in content or m in url for m in SPAM_MARKERS)


def _recency_bonus(date_str: str | None) -> float:
    """根据日期字符串给近期的加分（与 Cortex Scout recency_bonus 一致）。30 天内 0.25，1 年内 0.10。"""
    if not date_str or not str(date_str).strip():
        return 0.0
    s = str(date_str).strip()
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", s)
    if not m:
        return 0.0
    try:
        parsed = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    now = datetime.now(timezone.utc)
    delta = (now - parsed).days
    if delta < 0:
        return 0.05
    if delta <= 30:
        return 0.25
    if delta <= 365:
        return 0.10
    return 0.0


def _tokenize(text: str) -> list[str]:
    """分词：小写、按非字母数字/CJK 分割，过滤长度 ≤2 的 token（与 Cortex Scout rerank 一致）。"""
    if not text or not text.strip():
        return []
    s = (text or "").strip().lower()
    # 提取字母数字与 CJK 连续段
    tokens = re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+", s)
    return [t for t in tokens if len(t) > 2]


def _score_result(item: dict, query_tokens: list[str]) -> float:
    """
    计算单条结果与查询的词汇相关分 0.0~1.0。
    标题匹配 0.4/词，正文匹配 0.2/词，归一化后与匹配率结合（与 Cortex Scout rerank 一致）。
    """
    if not query_tokens:
        return 0.5
    title = (item.get("title") or "").strip()
    content = (item.get("content") or "").strip()
    title_tokens = set(_tokenize(title))
    content_tokens = set(_tokenize(content))
    score = 0.0
    matches = 0
    for qt in query_tokens:
        if qt in title_tokens:
            score += TITLE_WEIGHT
            matches += 1
        elif qt in content_tokens:
            score += CONTENT_WEIGHT
            matches += 1
    max_score = len(query_tokens) * TITLE_WEIGHT
    normalized = min(score / max_score, 1.0) if max_score > 0 else 0.5
    match_ratio = matches / len(query_tokens)
    final_score = (normalized + match_ratio) / 2.0
    return max(0.0, min(1.0, final_score))


def sort_by_relevance(
    items: list[dict], query: str, *, threshold: float | None = None
) -> list[dict]:
    """
    重排序：Reranker 分 → 关键词前置加分 → domain_weight → 垃圾过滤 → 按最终分+域优先级排序。
    与 Cortex Scout 一致。
    """
    q = (query or "").strip()
    if not q:
        return items

    query_tokens = _tokenize(q)
    early_tokens = [w for w in q.lower().split() if len(w) > 2] if q else []

    scored: list[tuple[dict, float]] = []
    for item in items:
        if _is_spammy(item):
            continue
        s = _score_result(item, query_tokens)
        if threshold is not None and s < threshold:
            continue
        content_preview = ((item.get("content") or "")[:EARLY_CONTENT_CHARS]).lower()
        early_matches = sum(1 for t in early_tokens if t in content_preview)
        if early_matches > 0:
            s *= 1.0 + EARLY_BOOST_FACTOR * early_matches
        domain, source_type = _classify_source_type(item.get("url") or "")
        dw = _domain_weight(q, domain, source_type)
        final_score = s * dw
        recency = _recency_bonus(item.get("date") or item.get("published_at"))
        final_score += recency
        scored.append((item, final_score))

    scored.sort(key=lambda x: (-x[1], -_domain_priority((x[0].get("url") or ""))))

    out = []
    for item, s in scored:
        row = dict(item)
        row["score"] = round(s, 4)
        out.append(row)
    return out


def _keyword_coverage(query: str) -> list[str]:
    """从 query 中提取可用于保底的关键词（简单按空格/标点分）。"""
    s = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", query)
    return [w.strip() for w in s.split() if len(w.strip()) >= 2]


def filter_and_keep_per_keyword(
    items: list[dict], query: str, *, max_items: int = 20
) -> list[dict]:
    """过滤低质量项，保证每个关键词至少保留一条，总条数不超过 max_items。"""
    keywords = _keyword_coverage(query)
    kept: list[dict] = []
    used_urls: set[str] = set()
    keyword_covered = {k: False for k in keywords}

    def has_keyword(text: str) -> str | None:
        text = (text or "").lower()
        for k in keywords:
            if k.lower() in text:
                return k
        return None

    for item in items:
        url = (item.get("url") or "").strip()
        if not url or url in used_urls:
            continue
        title = (item.get("title") or "").strip()
        content = (item.get("content") or "").strip()
        text = title + " " + content
        k = has_keyword(text)
        if k and not keyword_covered.get(k):
            keyword_covered[k] = True
            used_urls.add(url)
            kept.append(item)

    for item in items:
        url = (item.get("url") or "").strip()
        if not url or url in used_urls:
            continue
        if not (item.get("title") or item.get("url")):
            continue
        used_urls.add(url)
        kept.append(item)

    return kept[:max_items]


def run_pipeline(
    items: list[dict],
    query: str,
    *,
    max_items: int = 20,
    relevance_threshold: float | None = None,
) -> list[dict]:
    """去重 → 重排序(Reranker) → 过滤与保底，返回处理后的列表。"""
    items = dedupe_by_url(items)
    items = sort_by_relevance(items, query, threshold=relevance_threshold)
    items = filter_and_keep_per_keyword(items, query, max_items=max_items)
    return items
