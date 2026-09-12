"""Semantic half of the hybrid: meaning-based matching, fully local.

Primary encoder: sentence-transformers `all-MiniLM-L6-v2`. 384-dim sentence
embeddings, ~90MB, downloaded once from HuggingFace and cached on disk. After
that first download it runs 100% offline on CPU. No API key, no LLM call, no
paid service - the model weights sit on the laptop and we do the maths.

Fallback encoder: TF-IDF -> TruncatedSVD (Latent Semantic Analysis) fitted on
the actual JD + resume pool. Pure scikit-learn, no downloads. Weaker, but it
guarantees the demo runs even with no network at the venue.

The important design choice is CHUNK-LEVEL matching. Averaging a 3-page resume
into one vector washes out the two lines that actually matter. Instead we embed
every bullet, compare each JD requirement against every bullet, and keep the
best-matching bullets - which doubles as the evidence we quote in explanations.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np

from ..config import (
    ALLOW_LSA_FALLBACK,
    EMBEDDING_MODEL,
    FORCE_LSA,
    SEMANTIC_TOP_K_CHUNKS,
)


# ---------------------------------------------------------------------------
# Encoders
# ---------------------------------------------------------------------------
class Encoder:
    name = "base"
    # Cosine band used to map raw similarity onto a readable 0-1 scale, plus the
    # bar a similarity must clear to count as evidence for a *named* skill.
    # These differ per encoder because the two produce very differently shaped
    # similarity distributions - MiniLM cosines are low and spread, LSA cosines
    # are high and bunched. Calibrating per encoder is what keeps the final
    # scores comparable no matter which one loaded.
    cos_floor = 0.08
    cos_ceil = 0.62
    skill_threshold = 0.45

    def encode(self, texts: list[str]) -> np.ndarray:      # pragma: no cover
        raise NotImplementedError


class MiniLMEncoder(Encoder):
    name = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        from sentence_transformers import SentenceTransformer  # type: ignore

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.model = SentenceTransformer(model_name, device="cpu")
        self.name = model_name

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        vecs = self.model.encode(
            texts, batch_size=64, convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False,
        )
        return vecs.astype(np.float32)


class LSAEncoder(Encoder):
    """TF-IDF + SVD fitted on this batch. Deterministic, dependency-light."""

    name = "tfidf+svd (LSA fallback)"
    cos_floor = 0.05
    cos_ceil = 0.45
    skill_threshold = 0.60

    def __init__(self, corpus: list[str], n_components: int = 160):
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        corpus = [c for c in corpus if c.strip()] or ["empty"]
        self.vectorizer = TfidfVectorizer(
            lowercase=True, sublinear_tf=True, ngram_range=(1, 2),
            min_df=1, max_df=0.9, stop_words="english",
            token_pattern=r"(?u)\b[a-zA-Z0-9][a-zA-Z0-9+#./_-]+\b",
        )
        matrix = self.vectorizer.fit_transform(corpus)
        k = max(2, min(n_components, matrix.shape[1] - 1, matrix.shape[0] - 1))
        self.svd = TruncatedSVD(n_components=k, random_state=42)
        self.svd.fit(matrix)

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.svd.n_components), dtype=np.float32)
        vecs = self.svd.transform(self.vectorizer.transform(texts))
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (vecs / norms).astype(np.float32)


def build_encoder(corpus: list[str]) -> tuple[Encoder, list[str]]:
    """Return the best available encoder plus any notes for the user."""
    notes: list[str] = []
    if not FORCE_LSA:
        try:
            enc = MiniLMEncoder()
            return enc, notes
        except ImportError:
            notes.append("sentence-transformers not installed.")
        except Exception as exc:
            notes.append(f"Could not load '{EMBEDDING_MODEL}': {exc}")
    if not ALLOW_LSA_FALLBACK and not FORCE_LSA:
        raise RuntimeError("Embedding model unavailable and LSA fallback disabled. " + " ".join(notes))
    if notes:
        notes.append("Falling back to TF-IDF+SVD (LSA). Semantic quality will be lower.")
    return LSAEncoder(corpus), notes


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
# Raw MiniLM cosine between a JD bullet and a good resume bullet typically sits
# around 0.35-0.65; unrelated text sits near 0.0-0.15. Mapping that band onto
# 0-1 keeps the final scores readable instead of everything landing at "0.42".
def calibrate(sim: float, floor: float = 0.08, ceil: float = 0.62) -> float:
    return float(np.clip((sim - floor) / (ceil - floor), 0.0, 1.0))


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
@dataclass
class RequirementMatch:
    requirement: str
    kind: str
    similarity: float            # calibrated 0-1
    raw_cosine: float
    evidence: str                # the resume line that matched best
    evidence_section: str


@dataclass
class SemanticResult:
    score: float                 # 0-1
    matches: list[RequirementMatch] = field(default_factory=list)
    best_matches: list[RequirementMatch] = field(default_factory=list)
    weak_requirements: list[RequirementMatch] = field(default_factory=list)


class SemanticMatcher:
    """Encodes everything once, then answers per-resume queries cheaply."""

    def __init__(self, jd, resumes, encoder: Encoder | None = None):
        self.jd = jd
        self.resumes = resumes

        self.req_texts: list[str] = []
        self.req_kinds: list[str] = []
        for r in jd.requirements:
            self.req_texts.append(r.text)
            self.req_kinds.append(r.kind)
        if not self.req_texts:
            self.req_texts = [jd.raw_text[:1500]]
            self.req_kinds = ["required"]

        self.notes: list[str] = []
        if encoder is not None:
            self.encoder = encoder
        else:
            corpus = self.req_texts + [c.text for r in resumes for c in r.chunks]
            self.encoder, self.notes = build_encoder(corpus)

        self.req_vecs = self.encoder.encode(self.req_texts)
        self._chunk_cache: dict[str, np.ndarray] = {}
        self._skill_vec_cache: dict[str, np.ndarray] = {}
        self._agg_cache: dict[str, np.ndarray] = {}

        # Adaptive calibration. Raw cosine has no absolute meaning and its scale
        # differs wildly between MiniLM and the LSA fallback, so instead of
        # hard-coding a band we read it off THIS batch: the 15th percentile of
        # observed requirement-vs-resume similarity becomes 0, the 90th becomes
        # 1. Rank order is untouched (it is a monotone map) but the numbers
        # become readable and comparable no matter which encoder loaded.
        self.cos_floor, self.cos_ceil = self._calibration_band()

    def _calibration_band(self) -> tuple[float, float]:
        pooled: list[float] = []
        for resume in self.resumes:
            agg = self._aggregate(resume)
            if agg.size:
                pooled.extend(agg.tolist())
        if len(pooled) < 8:
            return self.encoder.cos_floor, self.encoder.cos_ceil
        arr = np.asarray(pooled, dtype=np.float64)
        floor = float(np.percentile(arr, 15))
        ceil = float(np.percentile(arr, 90))
        if ceil - floor < 0.02:                      # degenerate, everything alike
            return self.encoder.cos_floor, self.encoder.cos_ceil
        return floor, ceil

    # -- helpers ------------------------------------------------------------
    def _chunk_vectors(self, resume) -> np.ndarray:
        if resume.doc_id not in self._chunk_cache:
            texts = [c.text for c in resume.chunks] or [resume.raw_text[:1000]]
            self._chunk_cache[resume.doc_id] = self.encoder.encode(texts)
        return self._chunk_cache[resume.doc_id]

    def _chunk_meta(self, resume):
        return resume.chunks or []

    # -- aggregation --------------------------------------------------------
    def _aggregate_full(self, resume):
        """Per-requirement aggregated similarity + the chunk backing each one.

        For every JD requirement, take the top-k best-matching resume chunks,
        weight each by the section it came from (a line under "Projects"
        outweighs one under "Hobbies") and by rank (the single best match
        dominates), then average. Returns (agg, best_idx, raw_best).
        """
        chunk_vecs = self._chunk_vectors(resume)
        chunks = self._chunk_meta(resume)
        empty = np.zeros(0, dtype=np.float32)
        if chunk_vecs.size == 0 or self.req_vecs.size == 0:
            return empty, empty, empty

        sims = self.req_vecs @ chunk_vecs.T                  # (n_reqs, n_chunks)
        n_chunks = sims.shape[1]
        k = min(SEMANTIC_TOP_K_CHUNKS, n_chunks)

        sec_w = np.array([c.weight for c in chunks[:n_chunks]], dtype=np.float32)
        if sec_w.shape[0] < n_chunks:
            sec_w = np.pad(sec_w, (0, n_chunks - sec_w.shape[0]), constant_values=0.7)

        order = np.argsort(-sims, axis=1)[:, :k]
        decay = np.array([1.0 / (1 + 0.5 * r) for r in range(k)], dtype=np.float32)

        picked = np.take_along_axis(sims, order, axis=1)
        agg = (picked * sec_w[order] * decay).sum(axis=1) / (float(decay.sum()) or 1.0)
        return agg.astype(np.float32), order[:, 0], picked[:, 0].astype(np.float32)

    def _aggregate(self, resume) -> np.ndarray:
        if resume.doc_id not in self._agg_cache:
            self._agg_cache[resume.doc_id] = self._aggregate_full(resume)[0]
        return self._agg_cache[resume.doc_id]

    # -- public -------------------------------------------------------------
    def score_resume(self, resume) -> SemanticResult:
        chunks = self._chunk_meta(resume)
        agg, best_idx, raw_best = self._aggregate_full(resume)
        if agg.size == 0:
            return SemanticResult(score=0.0)

        matches: list[RequirementMatch] = []
        weights: list[float] = []
        values: list[float] = []

        for i, req_text in enumerate(self.req_texts):
            best_j = int(best_idx[i])
            match = RequirementMatch(
                requirement=req_text,
                kind=self.req_kinds[i],
                similarity=calibrate(float(agg[i]), self.cos_floor, self.cos_ceil),
                raw_cosine=round(float(raw_best[i]), 4),
                evidence=(chunks[best_j].text if best_j < len(chunks) else "")[:220],
                evidence_section=(chunks[best_j].section if best_j < len(chunks) else "other"),
            )
            matches.append(match)
            weights.append(1.6 if self.req_kinds[i] == "required" else 0.8)
            values.append(match.similarity)

        total_w = sum(weights) or 1.0
        score = float(sum(v * w for v, w in zip(values, weights)) / total_w)

        ranked = sorted(matches, key=lambda m: -m.similarity)
        weak = [m for m in sorted(matches, key=lambda m: m.similarity)
                if m.kind == "required" and m.similarity < 0.35]

        return SemanticResult(
            score=round(score, 4),
            matches=matches,
            best_matches=ranked[:5],
            weak_requirements=weak[:5],
        )

    def skill_evidence(self, resume, skill_key: str, skill_phrase: str) -> tuple[float, str]:
        """How strongly does this resume *imply* a skill it never names?

        Used for partial credit: a candidate who wrote "built and deployed
        containerised services" without ever typing "Docker" is not a zero on
        Docker, but they are not a full match either.
        """
        if skill_key not in self._skill_vec_cache:
            probe = f"experience with {skill_phrase}"
            self._skill_vec_cache[skill_key] = self.encoder.encode([probe])[0]
        vec = self._skill_vec_cache[skill_key]

        chunk_vecs = self._chunk_vectors(resume)
        if chunk_vecs.size == 0:
            return 0.0, ""
        sims = chunk_vecs @ vec
        j = int(np.argmax(sims))
        chunks = self._chunk_meta(resume)
        evidence = chunks[j].text[:200] if j < len(chunks) else ""
        return float(sims[j]), evidence
