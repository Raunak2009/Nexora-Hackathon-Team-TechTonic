"""Keyword half of the hybrid: a hand-written BM25 over the resume batch.

Why BM25 and not just TF-IDF cosine:
  * term-frequency saturation - a resume that says "Selenium" 40 times should
    not beat one that says it 4 times by 10x. BM25's k1 caps that.
  * length normalisation - a 5-page resume naturally contains more of every
    term. BM25's b discounts by document length, so short sharp resumes are
    not punished for being short.
  * IDF - "JavaScript" in a JD is a weak discriminator when every resume has
    it; "Kubernetes" is a strong one. IDF handles that automatically from the
    actual candidate pool, not from a hard-coded list.

It is implemented from scratch (no rank_bm25 dependency) so that during judging
you can point at the formula and explain exactly what your system computed.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from ..config import BM25_B, BM25_K1

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "so", "as", "of", "in",
    "on", "at", "to", "for", "with", "by", "from", "into", "about", "over", "under",
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does", "did",
    "have", "has", "had", "having", "will", "would", "shall", "should", "can", "could",
    "may", "might", "must", "this", "that", "these", "those", "it", "its", "we", "our",
    "you", "your", "they", "their", "he", "she", "his", "her", "i", "me", "my",
    "who", "whom", "which", "what", "when", "where", "how", "why", "all", "any",
    "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "too", "very", "s", "t", "just", "also", "well",
    "using", "use", "used", "work", "working", "years", "year", "role", "team",
    "company", "job", "position", "candidate", "applicant", "etc", "including",
    "good", "strong", "excellent", "ability", "able", "new", "across",
}

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#./_-]*")


def tokenize(text: str) -> list[str]:
    """Lowercase, keep tech punctuation (c++, node.js, ci/cd), drop stopwords."""
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        tok = raw.strip("./-_")
        if not tok or tok in STOPWORDS or len(tok) < 2 and tok not in {"c", "r"}:
            continue
        if tok.isdigit() and len(tok) == 4:      # bare years: 2016, 2021
            continue
        tokens.append(tok)
    return tokens


@dataclass
class LexicalResult:
    raw_score: float
    normalized: float                      # 0-1 within this batch
    top_terms: list[tuple[str, float]] = field(default_factory=list)
    matched_terms: set[str] = field(default_factory=set)
    missing_terms: list[str] = field(default_factory=list)


class BM25:
    def __init__(self, documents: list[list[str]], k1: float = BM25_K1, b: float = BM25_B):
        self.k1, self.b = k1, b
        self.docs = documents
        self.n = len(documents)
        self.doc_len = [len(d) for d in documents]
        self.avgdl = (sum(self.doc_len) / self.n) if self.n else 0.0
        self.tf: list[Counter] = [Counter(d) for d in documents]

        df: Counter = Counter()
        for counter in self.tf:
            df.update(counter.keys())
        self.df = df

        # Robertson/Sparck-Jones IDF with the +1 smoothing that keeps it
        # non-negative even for terms present in every document.
        self.idf = {
            term: math.log(1 + (self.n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def term_score(self, term: str, doc_index: int) -> float:
        f = self.tf[doc_index].get(term, 0)
        if f == 0:
            return 0.0
        idf = self.idf.get(term, math.log(1 + self.n))
        denom = f + self.k1 * (1 - self.b + self.b * self.doc_len[doc_index] / (self.avgdl or 1))
        return idf * (f * (self.k1 + 1)) / denom

    def score(self, query_terms: dict[str, float], doc_index: int) -> tuple[float, list[tuple[str, float]]]:
        contributions: list[tuple[str, float]] = []
        total = 0.0
        for term, weight in query_terms.items():
            s = self.term_score(term, doc_index) * weight
            if s > 0:
                contributions.append((term, s))
                total += s
        contributions.sort(key=lambda kv: -kv[1])
        return total, contributions


def build_query_terms(jd, ontology) -> dict[str, float]:
    """Weighted bag of query terms from the JD.

    Terms that name a REQUIRED skill (and their aliases) are boosted, so BM25
    is not just "which resume reuses the JD's prose" but "which resume reuses
    the JD's prose *where it matters*".
    """
    weights: dict[str, float] = {}

    def bump(text: str, weight: float) -> None:
        for tok in tokenize(text):
            weights[tok] = max(weights.get(tok, 0.0), weight)

    bump(jd.raw_text, 1.0)
    for req in jd.requirements:
        bump(req.text, 1.6 if req.kind == "required" else 1.1)
    for hit in jd.preferred_skills:
        node = ontology.get(hit.key)
        bump(hit.key, 2.0)
        if node:
            for alias in node.aliases:
                bump(alias, 2.0)
    for hit in jd.required_skills:
        node = ontology.get(hit.key)
        bump(hit.key, 3.0)
        if node:
            for alias in node.aliases:
                bump(alias, 3.0)
    return weights


def score_batch(jd, resumes, ontology) -> dict[str, LexicalResult]:
    """BM25 every resume against the JD, normalised within the batch."""
    docs = [tokenize(r.raw_text) for r in resumes]
    bm25 = BM25(docs)
    query = build_query_terms(jd, ontology)

    raw: list[tuple[float, list[tuple[str, float]]]] = [
        bm25.score(query, i) for i in range(len(resumes))
    ]
    scores = [r[0] for r in raw] or [0.0]

    # Normalise against the best resume in the pool. This is a *ranking*
    # problem - "how does this candidate compare to the others we have" is the
    # honest reading of a BM25 number, which has no absolute scale.
    best = max(scores) or 1.0

    results: dict[str, LexicalResult] = {}
    for i, resume in enumerate(resumes):
        total, contributions = raw[i]
        matched = {t for t, _ in contributions}
        important = [t for t, w in sorted(query.items(), key=lambda kv: -kv[1])[:40] if w >= 2.0]
        results[resume.doc_id] = LexicalResult(
            raw_score=round(total, 3),
            normalized=round(min(1.0, total / best), 4),
            top_terms=[(t, round(s, 3)) for t, s in contributions[:10]],
            matched_terms=matched,
            missing_terms=[t for t in important if t not in matched][:10],
        )
    return results
