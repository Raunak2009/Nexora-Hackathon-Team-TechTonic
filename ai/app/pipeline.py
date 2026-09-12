"""End-to-end pipeline: JD + resume batch -> ranked, explained shortlist."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Iterable

from .config import SIMPLE_WEIGHTS, WEIGHTS, SimpleWeights, Weights
from .matching.bias import audit_jd
from .matching.explain import compare_candidates, explain_candidate, explain_top_n
from .matching.score import rank_candidates
from .matching.semantic import SemanticMatcher
from .parsing.extract import ExtractedDocument, extract_document, extract_folder, normalize_text
from .parsing.jd import parse_jd
from .parsing.resume import Resume, parse_resume


class ShortlistEngine:
    """Holds one JD + one resume pool, so follow-up questions are free."""

    def __init__(self, jd, resumes: list[Resume]):
        self.jd = jd
        self.resumes = _ensure_unique_ids(resumes)
        self.matcher = SemanticMatcher(jd, resumes)
        self.encoder_name = self.matcher.encoder.name
        self.encoder_notes = self.matcher.notes
        self.candidates = []
        self.simple_weights = SimpleWeights.from_weights(WEIGHTS)
        self._chat = None

    # -- construction -------------------------------------------------------
    @classmethod
    def from_paths(cls, jd_path: str | Path, resume_paths: Iterable[str | Path]) -> "ShortlistEngine":
        jd = parse_jd(jd_path)
        resumes = [parse_resume(p) for p in resume_paths]
        return cls(jd, resumes)

    @classmethod
    def from_folder(cls, jd_path: str | Path, resume_folder: str | Path) -> "ShortlistEngine":
        jd = parse_jd(jd_path)
        resumes = [parse_resume(doc) for doc in extract_folder(resume_folder)]
        return cls(jd, resumes)

    @classmethod
    def from_text(cls, jd_text: str, resumes_text: dict[str, str]) -> "ShortlistEngine":
        """For the API: raw strings in, no files on disk."""
        jd = parse_jd(jd_text)
        parsed = [
            parse_resume(
                ExtractedDocument(path=Path(name), text=normalize_text(body), method="inline"),
                doc_id=name,
            )
            for name, body in resumes_text.items()
        ]
        return cls(jd, parsed)

    # -- running ------------------------------------------------------------
    def run(self, weights: Weights | None = None, explain_top: int = 3):
        t0 = time.time()
        if weights is not None:
            self.simple_weights = SimpleWeights.from_weights(weights)
        self.candidates = rank_candidates(self.jd, self.resumes, self.matcher, weights or WEIGHTS)
        for c in self.candidates[:max(explain_top, 0)]:
            c.explanation = explain_candidate(c, self.jd)
        self.elapsed = round(time.time() - t0, 2)
        return self.candidates

    # -- output -------------------------------------------------------------
    def result(self, explain_top: int = 3, verbose: bool = False, include_bias: bool = True) -> dict:
        if not self.candidates:
            self.run(explain_top=explain_top)

        out = {
            "job_description": self.jd.to_dict(),
            "pool_size": len(self.resumes),
            "engine": {
                "semantic_encoder": self.encoder_name,
                "weights": self.simple_weights.to_weights().normalized(),
                "slider_weights": self.simple_weights.as_dict(),
                "notes": self.encoder_notes,
                "elapsed_seconds": getattr(self, "elapsed", None),
            },
            "ranking": [c.to_dict(verbose=verbose) for c in self.candidates],
            "top_explanations": explain_top_n(self.candidates, self.jd, explain_top),
        }
        if include_bias:
            out["jd_bias_audit"] = audit_jd(self.jd)

        parse_issues = [
            {"file": r.path.name, "warnings": r.warnings, "method": r.extraction_method}
            for r in self.resumes if r.warnings
        ]
        if parse_issues:
            out["parse_issues"] = parse_issues
        return out

    # -- views the UI consumes ----------------------------------------------
    def matrix(self, include_preferred: bool = True) -> dict:
        from .reporting.matrix import skill_matrix
        if not self.candidates:
            self.run()
        return skill_matrix(self.candidates, self.jd, include_preferred)

    def detail(self, who: str) -> dict | None:
        from .reporting.matrix import candidate_detail
        from .matching.explain import explain_candidate
        c = self.find(who)
        if c is None:
            return None
        if not c.explanation:
            c.explanation = explain_candidate(c, self.jd)
        return candidate_detail(c, self.jd)

    def charts(self, top_n: int = 10) -> dict:
        from .reporting.matrix import chart_data
        if not self.candidates:
            self.run()
        return chart_data(self.candidates, self.jd, top_n)

    def filtered(self, filters) -> list:
        from .reporting.matrix import apply_filters
        from .matching.skills import get_ontology
        if not self.candidates:
            self.run()
        return apply_filters(self.candidates, filters, get_ontology())

    def top_comparisons(self, n: int = 3) -> dict:
        """Every pairwise comparison among the top N, for the comparison page."""
        from .matching.explain import compare_candidates, explain_candidate
        if not self.candidates:
            self.run()
        top = self.candidates[:n]
        for c in top:
            if not c.explanation:
                c.explanation = explain_candidate(c, self.jd)

        pairs = []
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                a, b = top[i], top[j]
                a_sk = {m.canonical for m in a.matched_required}
                b_sk = {m.canonical for m in b.matched_required}
                pairs.append({
                    "a": a.resume.name, "a_rank": a.rank, "a_score": a.score,
                    "b": b.resume.name, "b_rank": b.rank, "b_score": b.score,
                    "score_gap": round(a.score - b.score, 2),
                    "only_a_has": sorted(a_sk - b_sk),
                    "only_b_has": sorted(b_sk - a_sk),
                    "both_have": sorted(a_sk & b_sk),
                    "subscore_deltas": {
                        k: round(a.contributions.get(k, 0) - b.contributions.get(k, 0), 2)
                        for k in ("required_skills", "semantic", "lexical",
                                  "preferred_skills", "experience")
                    },
                    "explanation": compare_candidates(a, b, self.jd),
                })

        return {
            "candidates": [
                {
                    "rank": c.rank, "candidate": c.resume.name, "file": c.resume.path.name,
                    "score": c.score,
                    "keyword_score": round(c.keyword_score * 100, 1),
                    "semantic_score": round(c.semantic_score * 100, 1),
                    "skill_score": round(c.subscores.required_skills * 100, 1),
                    "confidence": c.confidence.to_dict() if c.confidence else None,
                    "matched": [m.canonical for m in c.matched_required],
                    "missing": [m.canonical for m in c.missing_required],
                    "explanation": c.explanation,
                }
                for c in top
            ],
            "pairwise": pairs,
        }

    def timeline(self, who: str) -> dict | None:
        from .matching.timeline import analyse_timeline
        c = self.find(who)
        if c is None:
            return None
        flags, payload = analyse_timeline(c.resume, self.jd)
        payload["candidate"] = c.resume.name
        payload["rank"] = c.rank
        payload["flags"] = [f.to_dict() for f in flags]
        return payload

    def unique_candidates(self) -> list:
        """The ranking with duplicate copies of the same person removed.

        Ranks are RE-NUMBERED here, because a shortlist that reads 1, 2, 4, 7 is
        confusing. The underlying scores are untouched.
        """
        if not self.candidates:
            self.run()
        seen: set[str] = set()
        out = []
        for c in self.candidates:
            key = c.identity_group or c.resume.doc_id
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    def dedupe(self) -> dict:
        from .matching.dedupe import dedupe_report
        return dedupe_report(self.resumes)

    def flagged(self) -> list[dict]:
        if not self.candidates:
            self.run()
        return [
            {"rank": c.rank, "candidate": c.resume.name, "file": c.resume.path.name,
             "score": c.score, "flag_level": c.worst_flag,
             "flags": [f.to_dict() for f in c.integrity_flags]}
            for c in self.candidates if c.integrity_flags
        ]

    # -- re-weighting -------------------------------------------------------
    def reweight(self, *, keyword: float | None = None, semantic: float | None = None,
                 experience: float | None = None) -> list:
        """Recompute the ranking with new slider positions.

        Cheap: the embeddings and the parse are reused, only the fusion changes.
        """
        from .config import SimpleWeights
        sw = SimpleWeights.from_weights(WEIGHTS)
        if keyword is not None:
            sw.keyword = max(0.0, keyword)
        if semantic is not None:
            sw.semantic = max(0.0, semantic)
        if experience is not None:
            sw.experience = max(0.0, experience)
        self.simple_weights = sw
        return self.run(weights=sw.to_weights(), explain_top=3)

    def rerank_with_extra_requirements(self, text: str) -> dict | None:
        """Re-rank against the JD PLUS a free-text wish from the recruiter.

        The sentence is parsed into requirements exactly like a JD bullet, so
        "I want someone who has actually deployed something to production" is
        matched semantically against every resume bullet, and any technology it
        names is matched as a real required skill.
        """
        from .matching.score import rank_candidates
        from .matching.semantic import SemanticMatcher
        from .parsing.jd import parse_jd

        extra = parse_jd(text)
        if not extra.requirements and not extra.required_skills:
            return None

        before = {c.resume.doc_id: c.rank for c in self.candidates}

        merged = _merge_jd(self.jd, extra)
        matcher = SemanticMatcher(merged, self.resumes)
        ranked = rank_candidates(merged, self.resumes, matcher,
                                 self.simple_weights.to_weights())

        movements = []
        for c in ranked:
            was = before.get(c.resume.doc_id)
            if was and was != c.rank:
                movements.append({"candidate": c.resume.name, "from": was,
                                  "to": c.rank, "delta": was - c.rank})
        movements.sort(key=lambda m: -abs(m["delta"]))

        return {
            "extra_requirement": text,
            "skills_detected": [s.canonical for s in extra.required_skills],
            "requirement_lines": [r.text for r in extra.requirements],
            "ranking": [c.to_dict() for c in ranked],
            "movements": movements,
        }

    # -- Q&A for the recruiter chat layer -----------------------------------
    def chat(self, question: str) -> dict:
        from .matching.chat import RecruiterChat
        if not self.candidates:
            self.run()
        if self._chat is None:
            self._chat = RecruiterChat(self)
        return self._chat.ask(question).to_dict()

    def find(self, needle: str):
        needle = needle.strip().lower()
        for c in self.candidates:
            if needle in c.resume.name.lower() or needle in c.resume.path.name.lower() \
                    or needle == str(c.rank) or needle == c.resume.doc_id.lower() \
                    or needle == c.resume.path.stem.lower():
                return c
        # Loose second pass: any word of the query matching a name word.
        tokens = [t for t in re.split(r"\W+", needle) if len(t) > 2]
        for c in self.candidates:
            name_tokens = {t.lower() for t in c.resume.name.split()}
            stem_tokens = {t.lower() for t in re.split(r"\W+", c.resume.path.stem)}
            if tokens and (set(tokens) & (name_tokens | stem_tokens)):
                return c
        return None

    def why_above(self, a: str, b: str) -> str:
        ca, cb = self.find(a), self.find(b)
        if ca is None or cb is None:
            missing = a if ca is None else b
            return f"I don't have a candidate matching '{missing}' in this pool."
        return compare_candidates(ca, cb, self.jd)

    def why_ranked(self, who: str) -> str:
        c = self.find(who)
        if c is None:
            return f"I don't have a candidate matching '{who}' in this pool."
        if not c.explanation:
            c.explanation = explain_candidate(c, self.jd)
        return c.explanation


def run_shortlist(jd_path: str | Path, resume_folder: str | Path,
                  explain_top: int = 3, verbose: bool = False) -> dict:
    engine = ShortlistEngine.from_folder(jd_path, resume_folder)
    engine.run(explain_top=explain_top)
    return engine.result(explain_top=explain_top, verbose=verbose)


def _ensure_unique_ids(resumes: list[Resume]) -> list[Resume]:
    """Guarantee distinct doc_ids.

    Several caches in the engine are keyed on doc_id. A collision does not
    raise - it silently serves one resume's embeddings for another, which is
    the kind of bug that produces a plausible-looking wrong ranking.
    """
    seen: dict[str, int] = {}
    for r in resumes:
        if r.doc_id in seen:
            seen[r.doc_id] += 1
            r.doc_id = f"{r.doc_id}#{seen[r.doc_id]}"
        else:
            seen[r.doc_id] = 1
    return resumes


def _merge_jd(base, extra):
    """Combine a JD with an ad-hoc recruiter requirement into one query.

    The extra requirement is added as REQUIRED, because the recruiter just said
    out loud that they want it. Everything else about the JD is preserved.
    """
    import copy

    merged = copy.copy(base)
    merged.requirements = list(base.requirements) + [
        type(r)(text=r.text, kind="required", heading="recruiter request", skills=r.skills)
        for r in extra.requirements
    ]
    have = {s.key for s in base.required_skills}
    merged.required_skills = list(base.required_skills) + [
        s for s in extra.required_skills if s.key not in have
    ]
    merged.preferred_skills = [s for s in base.preferred_skills
                               if s.key not in {x.key for x in merged.required_skills}]
    return merged
