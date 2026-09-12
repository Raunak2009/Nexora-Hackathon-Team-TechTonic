"""Data shapes the recruiter UI renders: skill matrix, charts, filters.

Nothing here recomputes a score. Every number is read off the ranking that
already exists, so the table, the charts and the PDF can never disagree with
each other or with the engine.
"""

from __future__ import annotations

from dataclasses import dataclass

# What the UI paints for each skill cell.
CELL_STYLE = {
    "exact":    {"symbol": "check",  "colour": "green",  "label": "Has it"},
    "related":  {"symbol": "tilde",  "colour": "amber",  "label": "Adjacent skill"},
    "semantic": {"symbol": "tilde",  "colour": "amber",  "label": "Implied, not named"},
    "missing":  {"symbol": "cross",  "colour": "red",    "label": "No evidence"},
}


def skill_matrix(candidates, jd, include_preferred: bool = True) -> dict:
    """Candidate x skill grid.

    Columns are the JD's skills (required first, then preferred). Each cell
    carries the match status, the credit given, and the resume line the status
    came from - so hovering a cell can show the evidence instead of making the
    recruiter trust a tick.
    """
    columns: list[dict] = []
    for hit in jd.required_skills:
        columns.append({"key": hit.key, "label": hit.canonical, "kind": "required"})
    if include_preferred:
        for hit in jd.preferred_skills:
            columns.append({"key": hit.key, "label": hit.canonical, "kind": "preferred"})

    rows: list[dict] = []
    for c in candidates:
        by_key = {m.key: m for m in c.required_matches}
        by_key.update({m.key: m for m in c.preferred_matches})

        cells = []
        for col in columns:
            m = by_key.get(col["key"])
            status = m.status if m else "missing"
            cells.append({
                "skill": col["label"],
                "key": col["key"],
                "kind": col["kind"],
                "status": status,
                "credit": round(m.credit, 2) if m else 0.0,
                "importance": round(m.importance, 2) if m else 1.0,
                "evidence": (m.evidence if m else "")[:180],
                "section": m.evidence_section if m else "",
                "reason": m.reason if m else "",
                **CELL_STYLE[status],
            })

        req_cells = [x for x in cells if x["kind"] == "required"]
        rows.append({
            "rank": c.rank,
            "doc_id": c.resume.doc_id,
            "candidate": c.resume.name,
            "file": c.resume.path.name,
            "score": c.score,
            "keyword_score": round(c.keyword_score * 100, 1),
            "semantic_score": round(c.semantic_score * 100, 1),
            "confidence": round(c.confidence.score, 1) if c.confidence else None,
            "flag_level": c.worst_flag,
            "required_met": sum(1 for x in req_cells if x["status"] == "exact"),
            "required_partial": sum(1 for x in req_cells if x["status"] in ("related", "semantic")),
            "required_total": len(req_cells),
            "cells": cells,
        })

    # Which requirement is the pool weakest on? Useful signal for the recruiter:
    # if nobody has it, the JD may be asking for the wrong thing.
    coverage = []
    for col in columns:
        have = sum(1 for r in rows
                   for cell in r["cells"]
                   if cell["key"] == col["key"] and cell["status"] == "exact")
        coverage.append({
            "skill": col["label"], "key": col["key"], "kind": col["kind"],
            "candidates_with_skill": have,
            "pool_coverage_pct": round(100 * have / len(rows), 1) if rows else 0.0,
        })
    coverage.sort(key=lambda x: x["pool_coverage_pct"])

    return {
        "legend": CELL_STYLE,
        "columns": columns,
        "rows": rows,
        "pool_coverage": coverage,
        "scarcest_skills": [c["skill"] for c in coverage if c["kind"] == "required"][:3],
    }


def candidate_detail(candidate, jd) -> dict:
    """Everything the per-candidate skills page needs, in one payload."""
    c = candidate
    return {
        "rank": c.rank,
        "doc_id": c.resume.doc_id,
        "candidate": c.resume.name,
        "file": c.resume.path.name,
        "email": c.resume.email,
        "phone": c.resume.phone,
        "links": c.resume.links,
        "education": c.resume.education_label,
        "years_experience": c.resume.years_experience,
        "experience_source": c.resume.experience_source,
        "is_student_or_fresher": c.resume.is_student_or_fresher,

        "scores": {
            "final": c.score,
            "skill": round(c.subscores.required_skills * 100, 1),
            "keyword": round(c.keyword_score * 100, 1),
            "semantic": round(c.semantic_score * 100, 1),
            "preferred": round(c.subscores.preferred_skills * 100, 1),
            "lexical_bm25": round(c.subscores.lexical * 100, 1),
            "experience": round(c.subscores.experience * 100, 1),
        },
        "weighted_contributions": {k: round(v, 2) for k, v in c.contributions.items()},
        "confidence": c.confidence.to_dict() if c.confidence else None,
        "integrity_flags": [f.to_dict() for f in c.integrity_flags],

        "required_skills": [m.to_dict() for m in c.required_matches],
        "preferred_skills": [m.to_dict() for m in c.preferred_matches],

        "semantic_evidence": [
            {
                "jd_requirement": m.requirement,
                "resume_line": m.evidence,
                "section": m.evidence_section,
                "similarity": round(m.similarity, 3),
                "raw_cosine": m.raw_cosine,
            }
            for m in c.semantic_result.best_matches
        ],
        "weakest_requirements": [
            {"jd_requirement": m.requirement, "similarity": round(m.similarity, 3)}
            for m in c.semantic_result.weak_requirements
        ],
        "top_bm25_terms": [{"term": t, "contribution": s} for t, s in c.lexical_result.top_terms],
        "missing_jd_terms": c.lexical_result.missing_terms,

        "explanation": c.explanation,
        "parse_warnings": c.resume.warnings,
        "extraction_method": c.resume.extraction_method,
        "timeline": _timeline_payload(c.resume, jd),
    }


def _timeline_payload(resume, jd) -> dict:
    """Dated history of the candidate, for the timeline view and the date checks."""
    from ..matching.timeline import analyse_timeline

    try:
        flags, payload = analyse_timeline(resume, jd)
        payload["flags"] = [f.to_dict() for f in flags]
        return payload
    except Exception as exc:                        # noqa: BLE001
        return {"entries": [], "overlaps": [], "flags": [],
                "error": f"{type(exc).__name__}: {exc}"}


def chart_data(candidates, jd, top_n: int = 10) -> dict:
    """Ready-to-plot payloads. The frontend should not have to reshape these."""
    top = candidates[:top_n]

    return {
        "score_bars": {
            "type": "stacked_bar",
            "title": "Where each candidate's score comes from",
            "labels": [c.resume.name for c in top],
            "series": [
                {"name": "Required skills",
                 "data": [round(c.contributions.get("required_skills", 0), 2) for c in top]},
                {"name": "Semantic match",
                 "data": [round(c.contributions.get("semantic", 0), 2) for c in top]},
                {"name": "Keyword (BM25)",
                 "data": [round(c.contributions.get("lexical", 0), 2) for c in top]},
                {"name": "Preferred skills",
                 "data": [round(c.contributions.get("preferred_skills", 0), 2) for c in top]},
                {"name": "Experience",
                 "data": [round(c.contributions.get("experience", 0), 2) for c in top]},
            ],
            "note": "Bars sum to the final score. Any negative segment is the "
                    "critical-skill dampener.",
        },

        "radar": {
            "type": "radar",
            "title": "Score profile",
            "axes": ["Required skills", "Semantic", "Keyword (BM25)",
                     "Preferred skills", "Experience", "Confidence"],
            "series": [
                {
                    "name": c.resume.name,
                    "data": [
                        round(c.subscores.required_skills * 100, 1),
                        round(c.subscores.semantic * 100, 1),
                        round(c.subscores.lexical * 100, 1),
                        round(c.subscores.preferred_skills * 100, 1),
                        round(c.subscores.experience * 100, 1),
                        round(c.confidence.score, 1) if c.confidence else 0.0,
                    ],
                }
                for c in top[:5]
            ],
        },

        "keyword_vs_semantic": {
            "type": "scatter",
            "title": "Keyword match vs semantic match",
            "x_axis": "Keyword score",
            "y_axis": "Semantic score",
            "points": [
                {
                    "name": c.resume.name,
                    "x": round(c.keyword_score * 100, 1),
                    "y": round(c.semantic_score * 100, 1),
                    "size": round(c.confidence.score, 1) if c.confidence else 30,
                    "rank": c.rank,
                }
                for c in candidates
            ],
            "note": "Top-right = names the tools AND describes the work. "
                    "Bottom-right = keyword match with little substance behind it. "
                    "Top-left = does the work, uses different vocabulary.",
        },

        "skill_coverage": {
            "type": "bar",
            "title": "How much of the pool has each required skill",
            "labels": [s.canonical for s in jd.required_skills],
            "data": [
                round(100 * sum(
                    1 for c in candidates
                    if any(m.key == s.key and m.status == "exact" for m in c.required_matches)
                ) / max(1, len(candidates)), 1)
                for s in jd.required_skills
            ],
            "note": "A bar near zero means the JD is asking for something this "
                    "applicant pool does not have.",
        },

        "score_distribution": {
            "type": "histogram",
            "title": "Score spread across the pool",
            "scores": [c.score for c in candidates],
            "min": min((c.score for c in candidates), default=0),
            "max": max((c.score for c in candidates), default=0),
            "median": sorted(c.score for c in candidates)[len(candidates) // 2] if candidates else 0,
        },
    }


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
@dataclass
class Filters:
    min_score: float | None = None
    min_years: float | None = None
    max_years: float | None = None
    must_have_skills: list[str] | None = None      # ontology keys or canonical names
    any_of_skills: list[str] | None = None
    min_education: int | None = None               # 1 diploma, 2 bachelor, 3 master, 4 phd
    min_confidence: float | None = None
    hide_flagged: bool = False
    max_flag_severity: str | None = None           # "high" hides high-severity only
    freshers_only: bool = False
    search: str | None = None                      # substring over name / file / skills

    def describe(self) -> list[str]:
        out = []
        if self.min_score is not None:
            out.append(f"score >= {self.min_score}")
        if self.min_years is not None:
            out.append(f"experience >= {self.min_years} yrs")
        if self.max_years is not None:
            out.append(f"experience <= {self.max_years} yrs")
        if self.must_have_skills:
            out.append("must have: " + ", ".join(self.must_have_skills))
        if self.any_of_skills:
            out.append("any of: " + ", ".join(self.any_of_skills))
        if self.min_education is not None:
            out.append(f"education level >= {self.min_education}")
        if self.min_confidence is not None:
            out.append(f"confidence >= {self.min_confidence}")
        if self.hide_flagged:
            out.append("hide flagged candidates")
        if self.max_flag_severity:
            out.append(f"hide {self.max_flag_severity}-severity flags")
        if self.freshers_only:
            out.append("freshers / students only")
        if self.search:
            out.append(f"search '{self.search}'")
        return out


_SEV_RANK = {"high": 0, "medium": 1, "low": 2, "info": 3}


def apply_filters(candidates, filters: Filters, ontology=None) -> list:
    """Filter WITHOUT re-ranking - ranks stay as computed against the full pool.

    This matters: if a recruiter filters to '2+ years' they still want to see
    that a candidate was #3 out of everyone, not #1 out of the survivors.
    """
    def resolve(names: list[str]) -> set[str]:
        keys = set()
        for n in names:
            k = ontology.resolve(n) if ontology else None
            keys.add(k or n.strip().lower())
        return keys

    out = []
    for c in candidates:
        r = c.resume

        if filters.min_score is not None and c.score < filters.min_score:
            continue
        if filters.min_years is not None and r.years_experience < filters.min_years:
            continue
        if filters.max_years is not None and r.years_experience > filters.max_years:
            continue
        if filters.min_education is not None and r.education_level < filters.min_education:
            continue
        if filters.freshers_only and not r.is_student_or_fresher:
            continue
        if filters.min_confidence is not None:
            if not c.confidence or c.confidence.score < filters.min_confidence:
                continue
        if filters.hide_flagged and c.integrity_flags:
            continue
        if filters.max_flag_severity:
            cap = _SEV_RANK.get(filters.max_flag_severity, 0)
            if any(_SEV_RANK.get(f.severity, 3) <= cap for f in c.integrity_flags):
                continue
        if filters.must_have_skills:
            if not resolve(filters.must_have_skills) <= r.skill_keys:
                continue
        if filters.any_of_skills:
            if not (resolve(filters.any_of_skills) & r.skill_keys):
                continue
        if filters.search:
            needle = filters.search.lower()
            haystack = " ".join([
                r.name.lower(), r.path.name.lower(),
                " ".join(s.canonical.lower() for s in r.skills),
            ])
            if needle not in haystack:
                continue

        out.append(c)
    return out
