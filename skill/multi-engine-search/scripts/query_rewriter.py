"""
查询改写：技术/开发者类查询增强，中英文场景区分（参考 Cortex Scout）。
- best_query：用于本次实际搜索，短技术查询可自动加「文档」等。
- suggestions：供模型展示给用户的「可尝试的其它搜索词」，如「query 文档」「query site:docs.python.org」等，便于用户结果不足时换词再搜。
"""

from __future__ import annotations

# 开发者/技术类关键词：英文 + 中文（用于判定是否为技术查询）
DEV_KEYWORDS_EN = frozenset({
    "rust", "python", "javascript", "typescript", "golang", "java", "api", "sdk",
    "tutorial", "docs", "documentation", "error", "bug", "install", "how to",
    "github", "stackoverflow", "crate", "npm", "package",
})
DEV_KEYWORDS_ZH = frozenset({
    "教程", "文档", "错误", "异常", "接口", "安装", "代码", "官网", "网站",
    "如何", "怎么", "示例", "用法", "配置", "开发", "编程",
})

# 语言相关：中文建议词 vs 英文建议词（用于 suggestions 与 best_query）
# doc_word/tutorial_word 用于「可试试加文档/教程」；site_word 用于「可试试搜官网/网站」
SUGGEST_ZH = ("文档", "教程", "网站")
SUGGEST_EN = ("documentation", "tutorial", "website")

# 技术站点映射（site: 语法，供 suggestions 建议用户限定到官方文档/Stack Overflow）
SITE_BY_KEYWORD = {
    "rust": ["doc.rust-lang.org", "docs.rs"],
    "python": ["docs.python.org"],
    "javascript": ["developer.mozilla.org"],
    "typescript": ["typescriptlang.org"],
    "go": ["go.dev", "pkg.go.dev"],
    "golang": ["go.dev", "pkg.go.dev"],
    "error": ["stackoverflow.com"],
    "bug": ["stackoverflow.com"],
    "错误": ["stackoverflow.com"],
    "异常": ["stackoverflow.com"],
}


def _is_mainly_chinese(text: str) -> bool:
    """粗略判断文本是否以中文为主（用于选择建议词语言）。"""
    if not (text or text.strip()):
        return False
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    total = sum(1 for c in text if c.strip())
    if total == 0:
        return False
    return cjk / total >= 0.3 or cjk >= 2


def _is_developer_query(query: str) -> bool:
    """是否为技术/开发者相关查询。"""
    q = (query or "").lower().strip()
    if any(k in q for k in DEV_KEYWORDS_EN):
        return True
    if any(k in query for k in DEV_KEYWORDS_ZH):
        return True
    # 常见模式
    if "how to" in q or "how do" in q or "教程" in query or "文档" in query or "怎么" in query:
        return True
    return False


def _detected_keywords(query: str) -> list[str]:
    """检测到的技术关键词（用于改写与 suggestions/site: 建议）。"""
    q = (query or "").lower()
    out = []
    for k in DEV_KEYWORDS_EN:
        if k in q:
            out.append(k)
    for k in DEV_KEYWORDS_ZH:
        if k in query:
            out.append(k)
    return out


def rewrite_query(query: str) -> dict:
    """
    对查询做轻量改写与建议，中英文区分。
    返回: original, best_query（用于实际搜索）, suggestions（供模型展示的「可尝试的其它搜索词」）, is_developer_query。
    """
    query = (query or "").strip()
    if not query:
        return {
            "original": query,
            "best_query": query,
            "suggestions": [],
            "is_developer_query": False,
        }

    is_dev = _is_developer_query(query)
    mainly_zh = _is_mainly_chinese(query)
    doc_word, tutorial_word, site_word = SUGGEST_ZH if mainly_zh else SUGGEST_EN

    best_query = query
    suggestions: list[str] = []

    if not is_dev:
        return {
            "original": query,
            "best_query": best_query,
            "suggestions": [],
            "is_developer_query": False,
        }

    keywords = _detected_keywords(query)
    q_lower = query.lower()
    has_doc = (
        "doc" in q_lower or "文档" in query or "documentation" in q_lower
        or "教程" in query or "tutorial" in q_lower
    )

    # suggestions：供模型在回复中提示用户「若结果不够可尝试这些搜索」
    if not has_doc and keywords:
        suggestions.append(f"{query} {doc_word}")
        suggestions.append(f"{query} {tutorial_word}")
    # 技术词对应 site: 官方文档/仓库，便于用户限定到权威来源
    for kw in keywords:
        for site in SITE_BY_KEYWORD.get(kw, [])[:1]:
            if "site:" not in q_lower and "site:" not in query:
                suggestions.append(f"{query} site:{site}")
            break
    # 错误/异常类建议限定到 Stack Overflow
    error_like = any(
        x in q_lower or x in query
        for x in ("error", "bug", "错误", "异常", "报错")
    )
    if error_like and "stackoverflow" not in q_lower:
        suggestions.append(f"{query} site:stackoverflow.com")
    # 找官网/官方网站时，可建议加「网站」/ website
    if not any(w in query for w in ("官网", "网站", "website", "官方")):
        if keywords:
            suggestions.append(f"{query} {site_word}")

    # 自动改写 best_query：短技术查询可追加「文档」提高本次结果质量
    if mainly_zh:
        if ("文档" in query or "官方" in query) and not ("教程" in query):
            pass
        elif "官网" in query or "网站" in query:
            pass
        elif keywords and not has_doc and len(query) <= 20:
            best_query = f"{query} {doc_word}"
    else:
        if ("docs" in q_lower or "documentation" in q_lower) and not ("tutorial" in q_lower):
            pass
        elif keywords and not has_doc and len(query) <= 30:
            best_query = f"{query} {doc_word}"

    return {
        "original": query,
        "best_query": best_query,
        "suggestions": suggestions[:6],
        "is_developer_query": True,
    }
