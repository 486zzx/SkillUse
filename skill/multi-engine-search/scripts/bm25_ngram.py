"""
BM25 n-gram 过滤：
- 查询词沿用上游分词结果（keywords token）。
- 文档先做字符 n-gram，再按空格拼接喂给 BM25。
"""

from __future__ import annotations

import math
from typing import Sequence


def build_char_ngrams(text: str, n: int = 2) -> list[str]:
    s = "".join((text or "").lower().split())
    if not s:
        return []
    if len(s) <= n:
        return [s]
    return [s[i : i + n] for i in range(len(s) - n + 1)]


def query_terms_to_ngrams(query_terms: Sequence[str], n: int = 2) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for t in query_terms:
        token = (t or "").strip().lower()
        if not token:
            continue
        grams = [token] if len(token) <= n else build_char_ngrams(token, n=n)
        for g in grams:
            if g and g not in seen:
                seen.add(g)
                out.append(g)
    return out


def score_documents_with_bm25_ngrams(
    documents: Sequence[str], query_terms: Sequence[str], *, ngram_n: int = 2
) -> list[float]:
    docs = [" ".join(build_char_ngrams(d or "", n=ngram_n)) for d in documents]
    bm25_terms = query_terms_to_ngrams(query_terms, n=ngram_n)
    bm25 = BM25Substring(k1=1.5, b=0.75, case_sensitive=False).fit(docs)
    return bm25.get_scores(query="", query_terms=bm25_terms)


def _substring_count(text: str, term: str, case_sensitive: bool = False) -> int:
    if not term:
        return 0
    if not case_sensitive:
        text, term = text.lower(), term.lower()
    count = 0
    start = 0
    while True:
        pos = text.find(term, start)
        if pos == -1:
            break
        count += 1
        start = pos + len(term)
    return count


def _doc_contains_term(doc: str, term: str, case_sensitive: bool = False) -> bool:
    if not term:
        return False
    if not case_sensitive:
        doc, term = doc.lower(), term.lower()
    return term in doc


class BM25Substring:
    def __init__(self, k1: float = 1.5, b: float = 0.75, case_sensitive: bool = False):
        self.k1 = k1
        self.b = b
        self.case_sensitive = case_sensitive
        self._docs: list[str] = []
        self._avgdl: float = 0.0
        self._doc_lens: list[int] = []

    def fit(self, documents: Sequence[str]) -> BM25Substring:
        self._docs = [str(d).strip() for d in documents if d is not None]
        self._doc_lens = [len(d) for d in self._docs]
        n = len(self._docs)
        self._avgdl = sum(self._doc_lens) / n if n else 0.0
        return self

    def _compute_idf(self, query_terms: list[str]) -> dict[str, float]:
        n = len(self._docs)
        idf: dict[str, float] = {}
        for t in query_terms:
            if not t or t in idf:
                continue
            df = sum(1 for d in self._docs if _doc_contains_term(d, t, self.case_sensitive))
            idf[t] = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
        return idf

    def get_scores(self, query: str, query_terms: list[str] | None = None) -> list[float]:
        if not self._docs:
            return []
        terms = query_terms if query_terms is not None else [t for t in query.split() if t]
        if not terms:
            return [0.0] * len(self._docs)
        idf = self._compute_idf(terms)
        n = len(self._docs)
        scores = [0.0] * n
        for i, doc in enumerate(self._docs):
            doc_len = self._doc_lens[i]
            for t in terms:
                idf_t = idf.get(t, 0.0)
                if idf_t <= 0:
                    continue
                tf = _substring_count(doc, t, self.case_sensitive)
                if tf == 0:
                    continue
                norm = 1.0 - self.b + self.b * (doc_len / self._avgdl) if self._avgdl else 1.0
                scores[i] += idf_t * (tf * (self.k1 + 1)) / (tf + self.k1 * norm)
        return scores

