"""Score fusion: combine keyword, ontology and semantic evidence into a rank.

Final score (0-100) = weighted sum of five sub-scores, then a mild dampener if
the candidate misses most of the explicitly required skills.

  required_skills  0.34   ontology-aware coverage of must-have skills
  semantic         0.26   meaning-level match of resume bullets to JD bullets
  lexical          0.16   BM25 over the candidate pool
  preferred_skills 0.12   coverage of nice-to-haves
  experience       0.12   years + education fit against the stated bar

Every number a candidate receives is traceable to a line in their resume. That
is the whole point: the output is a shortlist a recruiter can argue with.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import (
    EXPERIENCE_OVERSHOOT_TOLERANCE,
    RELATED_SKILL_CREDIT,
    SEMANTIC_SKILL_CREDIT,
    SEMANTIC_SKILL_THRESHOLD,
    WEIGHTS,
)
from .integrity import check_integrity, score_confidence
from .lexical import LexicalResult, score_batch
from .semantic import SemanticMatcher, SemanticResult
from .skills import SkillOntology, get_ontology

STATUS_ORDER = {"exact": 0, "related": 1, "semantic": 2, "missing": 3}


@dataclass
class SkillMatch:
    key: str
    canonical: str
    status: str          # exact | related | semantic | missing
    credit: float        # 0-1 contribution toward coverage
    importance: float = 1.0   # how much this skill counts (soft skills count less)
    evidence: str = ""
    evidence_section: str = ""
    reason: str = ""

    @property
    def is_hard(self) -> bool:
        return self.importance >= 0.9

    def to_dict(self) -> dict:
        return {
            "skill": self.canonical,
            "status": self.status,
            "credit": round(self.credit, 3),
            "importance": self.importance,
            "evidence": self.evidence,
            "section": self.evidence_section,
            "reason": self.reason,
        }


@dataclass
class SubScores:
    required_skills: float = 0.0
    preferred_skills: float = 0.0
    semantic: float = 0.0
    lexical: float = 0.0
    experience: float = 0.0

    def keyword(self, weights: dict[str, float] | None = None) -> float:
        """The composite 'keyword score' the UI shows as one number.

        Skill coverage and BM25 are both keyword-side evidence; the recruiter
        does not want three sliders for them. Combined in the same proportion
        the fusion weights use, so this number is not a separate calculation -
        it is a view of the same one.
        """
        w = weights or {"required_skills": 0.34, "preferred_skills": 0.12, "lexical": 0.16}
        total = w["required_skills"] + w["preferred_skills"] + w["lexical"]
        if total <= 0:
            return 0.0
        return (self.required_skills * w["required_skills"]
                + self.preferred_skills * w["preferred_skills"]
                + self.lexical * w["lexical"]) / total

    def to_dict(self, weights: dict[str, float] | None = None) -> dict:
        d = {k: round(v, 4) for k, v in self.__dict__.items()}
        d["keyword"] = round(self.keyword(weights), 4)
        return d


@dataclass
class RankedCandidate:
    rank: int
    resume: object
    score: float                 # 0-100
    subscores: SubScores
    contributions: dict[str, float]
    required_matches: list[SkillMatch]
    preferred_matches: list[SkillMatch]
    semantic_result: SemanticResult
    lexical_result: LexicalResult
    experience_note: str
    critical_gaps: list[str] = field(default_factory=list)
    explanation: str = ""
    flags: list[str] = field(default_factory=list)
    integrity_flags: list = field(default_factory=list)     # list[Flag]
    identity_group: str = ""          # all copies of one person share this
    is_duplicate: bool = False        # a non-primary copy of another row
    duplicate_of: str = ""            # the file we kept instead
    duplicate_files: list = field(default_factory=list)   # other copies of THIS person
    confidence: object | None = None                        # Confidence
    weights_used: dict[str, float] = field(default_factory=dict)

    @property
    def keyword_score(self) -> float:
        return self.subscores.keyword(self.weights_used or None)

    @property
    def semantic_score(self) -> float:
        return self.subscores.semantic

    @property
    def worst_flag(self) -> str | None:
        for sev in ("high", "medium", "low"):
            for f in self.integrity_flags:
                if f.severity == sev:
                    return sev
        return None

    @property
    def matched_required(self) -> list[SkillMatch]:
        return [m for m in self.required_matches if m.status != "missing"]

    @property
    def missing_required(self) -> list[SkillMatch]:
        return [m for m in self.required_matches if m.status == "missing"]

    def to_dict(self, verbose: bool = False) -> dict:
        out = {
            "rank": self.rank,
            "candidate": self.resume.name,
            "file": self.resume.path.name,
            "doc_id": self.resume.doc_id,
            "email": self.resume.email,
            "score": self.score,
            "keyword_score": round(self.keyword_score * 100, 1),
            "semantic_score": round(self.semantic_score * 100, 1),
            "skill_score": round(self.subscores.required_skills * 100, 1),
            "subscores": self.subscores.to_dict(self.weights_used or None),
            "weighted_contributions": {k: round(v, 2) for k, v in self.contributions.items()},
            "matched_required_skills": [m.canonical for m in self.matched_required],
            "missing_required_skills": [m.canonical for m in self.missing_required],
            "matched_preferred_skills": [m.canonical for m in self.preferred_matches if m.status != "missing"],
            "years_experience": self.resume.years_experience,
            "education": self.resume.education_label,
            "explanation": self.explanation,
            "flags": self.flags,
            "integrity_flags": [f.to_dict() for f in self.integrity_flags],
            "flag_level": self.worst_flag,
            "confidence": self.confidence.to_dict() if self.confidence else None,
            "identity_group": self.identity_group,
            "is_duplicate": self.is_duplicate,
            "duplicate_of": self.duplicate_of,
            "duplicate_files": self.duplicate_files,
        }
        if verbose:
            out["required_skill_detail"] = [m.to_dict() for m in self.required_matches]
            out["preferred_skill_detail"] = [m.to_dict() for m in self.preferred_matches]
            out["top_semantic_evidence"] = [
                {
                    "jd_requirement": m.requirement,
                    "resume_line": m.evidence,
                    "section": m.evidence_section,
                    "similarity": round(m.similarity, 3),
                    "raw_cosine": m.raw_cosine,
                }
                for m in self.semantic_result.best_matches
            ]
            out["top_bm25_terms"] = self.lexical_result.top_terms
            out["experience_note"] = self.experience_note
            out["parse_warnings"] = self.resume.warnings
        return out


# ---------------------------------------------------------------------------
# Skill coverage
# ---------------------------------------------------------------------------

def match_skills(
    resume,
    jd_skill_keys: list[str],
    ontology: SkillOntology,
    matcher: SemanticMatcher | None,
) -> tuple[list[SkillMatch], float]:
    """Resolve each demanded skill against the resume, in decreasing strength.

    exact    - the resume names the skill (or an alias, or a near-typo of it)
    related  - the resume names an ontology neighbour (React <- Next.js)
    semantic - no name, but a resume line means it ("containerised services")
    missing  - no evidence at all
    """
    have = resume.skill_keys
    matches: list[SkillMatch] = []

    # A named skill must clear a different bar depending on which encoder
    # loaded - LSA cosines run much hotter than MiniLM's.
    threshold = getattr(getattr(matcher, "encoder", None), "skill_threshold",
                        SEMANTIC_SKILL_THRESHOLD)

    for key in jd_skill_keys:
        node = ontology.get(key)
        canonical = node.canonical if node else key
        importance = node.importance if node else 1.0
        hit = resume.skill(key)

        if hit is not None:
            matches.append(SkillMatch(
                key=key, canonical=canonical, status="exact", credit=1.0,
                importance=importance,
                evidence=hit.evidence, evidence_section=hit.section,
                reason=f"Resume explicitly lists '{hit.surface}'"
                       + (f" under {hit.section}" if hit.section != "other" else ""),
            ))
            continue

        neighbours = ontology.related_keys(key) & have
        if neighbours:
            best = sorted(neighbours)[0]
            n_hit = resume.skill(best)
            matches.append(SkillMatch(
                key=key, canonical=canonical, status="related",
                credit=RELATED_SKILL_CREDIT, importance=importance,
                evidence=n_hit.evidence if n_hit else "",
                evidence_section=n_hit.section if n_hit else "",
                reason=f"No direct mention of {canonical}, but has closely related "
                       f"{ontology.canonical(best)}",
            ))
            continue

        if matcher is not None:
            sim, evidence = matcher.skill_evidence(resume, key, canonical)
            if sim >= threshold:
                matches.append(SkillMatch(
                    key=key, canonical=canonical, status="semantic",
                    credit=SEMANTIC_SKILL_CREDIT * min(1.0, sim / max(threshold, 1e-6)),
                    importance=importance,
                    evidence=evidence,
                    reason=f"Never named, but a resume line is semantically close "
                           f"(cosine {sim:.2f} >= {threshold:.2f})",
                ))
                continue

        matches.append(SkillMatch(
            key=key, canonical=canonical, status="missing", credit=0.0,
            importance=importance,
            reason=f"No evidence of {canonical} anywhere in the resume",
        ))

    # Importance-weighted coverage: missing React should cost far more than
    # missing "teamwork", because one is a hiring decision and the other is a
    # line every resume contains anyway.
    denom = sum(m.importance for m in matches)
    coverage = (sum(m.credit * m.importance for m in matches) / denom) if denom else 0.0
    matches.sort(key=lambda m: (STATUS_ORDER[m.status], -m.importance, -m.credit))
    return matches, coverage


# ---------------------------------------------------------------------------
# Experience fit
# ---------------------------------------------------------------------------

def experience_fit(resume, jd) -> tuple[float, str]:
    years, need = resume.years_experience, jd.min_years

    if need <= 0:
        # No bar stated (typical for internships). Practical exposure of any
        # kind is a mild plus; absence of it is not disqualifying.
        fit = 0.62 + 0.38 * min(1.0, years / 1.5)
        note = (f"JD states no minimum experience. Candidate shows "
                f"{years:.1f} yrs ({resume.experience_source}).")
    else:
        ratio = years / need
        fit = 1.0 if ratio >= 1 else max(0.0, ratio) ** 0.7
        note = f"JD asks for {need:.0f}+ yrs; candidate shows {years:.1f} yrs."
        if jd.seniority in ("intern", "junior") and years > need + EXPERIENCE_OVERSHOOT_TOLERANCE:
            fit *= 0.85
            note += " Materially over the bar for a junior/intern role."

    # Education is a light modifier, not a gate.
    edu_target = 1 if jd.seniority == "intern" else 2
    edu_fit = 1.0 if resume.education_level >= edu_target else (0.6 if resume.education_level > 0 else 0.45)

    return round(0.78 * fit + 0.22 * edu_fit, 4), note


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def rank_candidates(jd, resumes, matcher: SemanticMatcher | None = None,
                    weights=None) -> list[RankedCandidate]:
    ontology = get_ontology()
    weights = (weights or WEIGHTS).normalized()

    if matcher is None:
        matcher = SemanticMatcher(jd, resumes)

    lexical = score_batch(jd, resumes, ontology)

    # Identity resolution: the same person often appears several times (the same
    # resume exported as .pdf, .docx, .txt and .xml, or a re-submission). Every
    # copy is still SCORED - dropping one before scoring would change BM25's IDF
    # and the semantic calibration - but each row knows whether it is the copy
    # we keep, so the UI can collapse them without distorting the maths.
    from .dedupe import group_identities

    identity: dict[str, tuple[str, bool, str, list]] = {}
    for group in group_identities(resumes):
        others = [r.path.name for r in group.members]
        for member in group.members:
            is_dupe = member.doc_id != group.primary.doc_id
            identity[member.doc_id] = (
                group.group_id, is_dupe,
                group.primary.path.name if is_dupe else "",
                [n for n in others if n != member.path.name],
            )

    results: list[RankedCandidate] = []
    for resume in resumes:
        req_matches, req_cov = match_skills(resume, jd.required_keys, ontology, matcher)
        pref_matches, pref_cov = match_skills(resume, jd.preferred_keys, ontology, matcher)
        sem = matcher.score_resume(resume)
        lex = lexical[resume.doc_id]
        exp_fit, exp_note = experience_fit(resume, jd)

        sub = SubScores(
            required_skills=req_cov,
            preferred_skills=pref_cov if jd.preferred_keys else 0.5,
            semantic=sem.score,
            lexical=lex.normalized,
            experience=exp_fit,
        )

        contributions = {k: getattr(sub, k) * w * 100 for k, w in weights.items()}
        score = sum(contributions.values())

        # Dampener: the JD named specific must-haves and this candidate has
        # almost none of them by name. Semantic similarity alone must not be
        # able to float such a candidate to the top - the problem statement is
        # explicit that a role asking for certain skills "shouldn't be
        # satisfied by only loosely related experience".
        # Only HARD skills count here - being short on "teamwork" is not a
        # critical gap, being short on React for a React role is.
        hard = [m for m in req_matches if m.is_hard]
        exact_ratio = (
            sum(1 for m in hard if m.status == "exact") / len(hard) if hard else 1.0
        )
        if hard and exact_ratio < 0.5:
            damp = 0.78 + 0.44 * exact_ratio
            before = score
            score *= damp
            contributions["critical_skill_dampener"] = round(score - before, 2)

        flags: list[str] = []
        if resume.warnings:
            flags.append("parsing warnings - verify manually")
        if not resume.skills:
            flags.append("no recognised skills extracted")
        if len(resume.raw_text) < 400:
            flags.append("very short / possibly unreadable resume")

        results.append(RankedCandidate(
            rank=0, resume=resume, score=round(score, 2), subscores=sub,
            contributions=contributions, required_matches=req_matches,
            preferred_matches=pref_matches, semantic_result=sem, lexical_result=lex,
            experience_note=exp_note,
            critical_gaps=[m.canonical for m in req_matches if m.status == "missing"],
            flags=flags,
            identity_group=identity.get(resume.doc_id, ("", False, "", []))[0],
            is_duplicate=identity.get(resume.doc_id, ("", False, "", []))[1],
            duplicate_of=identity.get(resume.doc_id, ("", False, "", []))[2],
            duplicate_files=identity.get(resume.doc_id, ("", False, "", []))[3],
            integrity_flags=check_integrity(resume, jd, pool=resumes),
            confidence=score_confidence(resume),
            weights_used=weights,
        ))

    results.sort(key=lambda c: (-c.score, c.is_duplicate, c.resume.name))
    for i, c in enumerate(results, start=1):
        c.rank = i
    return results
