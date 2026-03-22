"""
去重模块：URL 规范化、按 URL 去重、同 URL 多源合并、breadcrumbs 提取。
与 Cortex Scout 对齐：去掉追踪参数；去重时合并多引擎并保留更全 title/content；
从 URL 提取 host + 路径前几段作为 breadcrumbs。
"""

from __future__ import annotations

import urllib.parse

# 仅去掉明确仅用于追踪、不会区分页面内容的参数（不含 source，以免误合并不同来源同 path 的页面）
_STRIP_QUERY_KEYS = frozenset({
    "ref", "fbclid", "gclid", "yclid", "mc_cid", "mc_eid", "ref_src",
    "msclkid", "_ga", "_gid",  # Bing / Google Analytics 等纯追踪
})


def normalize_url(url: str) -> str:
    """规范化 URL：统一协议、去掉追踪参数、去掉 fragment、尾部斜杠。

    Examples:
        >>> normalize_url("https://example.com/article?utm_source=google&fbclid=abc")
        'https://example.com/article'
        >>> normalize_url("https://docs.site.com/page#section-1")
        'https://docs.site.com/page'
        >>> normalize_url("example.com/path")
        'https://example.com/path'
        >>> normalize_url("https://example.com/blog/")
        'https://example.com/blog'
        >>> normalize_url("https://shop.com/item?id=42&gclid=xyz")
        'https://shop.com/item?id=42'
        >>> normalize_url("")
        ''
    """
    if not url or not url.strip():
        return ""
    s = url.strip()
    try:
        parsed = urllib.parse.urlparse(s)
        if not parsed.scheme:
            s = "https://" + s
            parsed = urllib.parse.urlparse(s)
        parsed = parsed._replace(fragment="")
        q = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
        q = {
            k: v
            for k, v in q.items()
            if not (
                k.lower().startswith("utm_")
                or k.lower() in _STRIP_QUERY_KEYS
            )
        }
        new_query = urllib.parse.urlencode(q, doseq=True) if q else ""
        parsed = parsed._replace(query=new_query)
        path = parsed.path.rstrip("/") or "/"
        parsed = parsed._replace(path=path)
        return (
            urllib.parse.urlunparse(parsed).rstrip("/")
            if parsed.path != "/"
            else urllib.parse.urlunparse(parsed)
        )
    except Exception:
        return url


def breadcrumbs_from_url(url_str: str) -> list[str]:
    """从 URL 提取 host + 路径前几段作为面包屑（与 Cortex Scout 一致，便于展示）。"""
    if not url_str or not url_str.strip():
        return []
    try:
        parsed = urllib.parse.urlparse(url_str.strip())
        parts = []
        if parsed.hostname:
            parts.append(parsed.hostname.lower())
        path_segs = [s for s in (parsed.path or "").strip("/").split("/") if s][:3]
        parts.extend(path_segs)
        return parts
    except Exception:
        return []


def dedupe_by_url(items: list[dict]) -> list[dict]:
    """
    按规范化 URL 去重；同一 URL 来自多引擎时合并来源并保留更全的 title/content。
    输出项含 url（已规范）、sources（引擎列表）、search_keywords（命中该条时使用的关键词列表），不再输出冗余的 source 字符串。
    """
    merged: dict[str, dict] = {}
    for x in items:
        raw_url = (x.get("url") or "").strip()
        u = normalize_url(raw_url)
        if not u:
            continue
        src = (x.get("source") or "").strip() or "unknown"
        title = (x.get("title") or "").strip()
        content = (x.get("content") or "").strip()
        kw = (x.get("search_keyword") or "").strip()
        rank = x.get("stream_rank")
        if u not in merged:
            row = dict(x)
            row["url"] = u
            row["title"] = title
            row["content"] = content
            row["sources"] = [src]
            row["breadcrumbs"] = breadcrumbs_from_url(u)
            row["search_keywords"] = [kw] if kw else []
            row["stream_ranks"] = []
            if kw and isinstance(rank, int) and rank > 0:
                row["stream_ranks"].append({"source": src, "keyword": kw, "rank": rank})
            merged[u] = row
            continue
        acc = merged[u]
        if src not in acc["sources"]:
            acc["sources"].append(src)
        if kw and kw not in acc["search_keywords"]:
            acc["search_keywords"].append(kw)
        if kw and isinstance(rank, int) and rank > 0:
            found = False
            for sr in acc.get("stream_ranks", []):
                if sr.get("source") == src and sr.get("keyword") == kw:
                    sr["rank"] = min(int(sr.get("rank", rank)), rank)
                    found = True
                    break
            if not found:
                acc.setdefault("stream_ranks", []).append(
                    {"source": src, "keyword": kw, "rank": rank}
                )
        if len(title) > len(acc.get("title") or ""):
            acc["title"] = title
        if len(content) > len(acc.get("content") or ""):
            acc["content"] = content
        if acc.get("score") is None and x.get("score") is not None:
            acc["score"] = x["score"]
        if not (acc.get("date") or "").strip() and (x.get("date") or "").strip():
            acc["date"] = x.get("date") or ""
    out = []
    for acc in merged.values():
        if "breadcrumbs" not in acc:
            acc["breadcrumbs"] = breadcrumbs_from_url(acc.get("url") or "")
        acc.pop("source", None)  # 只保留 sources 数组
        acc.pop("search_keyword", None)  # 只保留 search_keywords 数组
        acc.pop("stream_rank", None)
        out.append(acc)
    return out


if __name__ == "__main__":
    # 可运行示例：python -m dedupe 或 pytest --doctest-modules dedupe.py
    assert normalize_url("https://example.com/article?utm_source=google&fbclid=abc") == "https://example.com/article"
    assert normalize_url("https://docs.site.com/page#section-1") == "https://docs.site.com/page"
    assert normalize_url("example.com/path") == "https://example.com/path"
    assert normalize_url("https://example.com/blog/") == "https://example.com/blog"
    assert normalize_url("https://shop.com/item?id=42&gclid=xyz") == "https://shop.com/item?id=42"
    assert normalize_url("") == ""
    assert normalize_url("  ") == ""
    print("dedupe.normalize_url examples OK")
