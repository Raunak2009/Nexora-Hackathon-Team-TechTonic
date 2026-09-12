"""Integrity flags and evidence-confidence scoring.

Two separate jobs that both answer "how much should the recruiter trust this
row of the ranking?":

INTEGRITY FLAGS - things that look wrong and deserve a human glance:
  * seniority mismatch   - an "intern" applicant with 5 years of industry work
  * keyword stuffing     - 30 technologies listed and no sentence describing any
  * impossible timeline  - dates that end before they start, or run into 2031
  * duplicate resume     - two near-identical submissions in the same pool
  * prompt injection     - text aimed at an AI screener rather than a human
  * unreadable           - the parser got almost nothing out of the file

CONFIDENCE - how well EVIDENCED the candidate's claims are. This measures the
resume, not the person: a resume that says "cut p95 latency from 800ms to 210ms"
is better evidence than one that says "good knowledge of performance". Two
candidates can have the same skill score and very different confidence, and that
difference is exactly what a recruiter wants to see before an interview.

All rule-based and auditable - every flag names the text that triggered it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import (
    KEYWORD_STUFF_MIN_SKILLS,
    KEYWORD_STUFF_WORDS_PER_SKILL,
    SENIORITY_CEILING,
)

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


@dataclass
class Flag:
    code: str
    severity: str          # high | medium | low | info
    title: str
    detail: str
    evidence: str = ""

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
# Text written to manipulate an automated screener rather than inform a human.
INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?",
    r"disregard\s+(?:all\s+)?(?:previous|prior|the\s+above)",
    r"you\s+are\s+(?:an?\s+)?(?:ai|assistant|language\s+model|chatbot)",
    r"(?:rank|rate|score|select|shortlist)\s+(?:this|me|the)\s+"
    r"(?:candidate|resume|applicant)?\s*(?:as\s+)?(?:first|top|highest|number\s*1|100)",
    r"(?:give|assign)\s+(?:this\s+)?(?:resume|candidate|me)\s+(?:a\s+)?"
    r"(?:score\s+of\s+)?(?:100|full\s+marks|maximum)",
    r"system\s*(?:prompt|message)\s*:",
    r"<\s*/?\s*(?:system|instruction|prompt)\s*>",
    r"as\s+an\s+ai\s+(?:model|assistant)\s*,?\s*you\s+(?:must|should)",
    r"this\s+candidate\s+is\s+(?:the\s+)?(?:best|perfect|ideal)\s+(?:match|fit)\s+for",
]
_INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in INJECTION_PATTERNS), re.I)

# Claims with no substance behind them.
_SUPERLATIVE_RE = re.compile(
    r"\b(expert|mastery|master|guru|ninja|rockstar|world[\s-]class|unparalleled|"
    r"exceptional|outstanding|best[\s-]in[\s-]class|10x\s+(?:developer|engineer))\b", re.I)

# Evidence of real, measurable work.
_QUANTIFIED_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*%"                                     # 74%, 31.5%
    r"|\b\d+(?:\.\d+)?\s*[km]\b"                              # 12k, 1.5M
    r"|\b\d{2,}\+?(?:\s+\w+){0,2}\s+"                         # 900+ problems, 12k daily requests
    r"(?:users?|requests?|records?|customers?|students?|downloads?|hours?|"
    r"seconds?|queries|tests?|bugs?|commits?|problems?|projects?|articles?|"
    r"posts?|clients?|transactions?|rows?|endpoints?|screens?|components?)\b"
    r"|\b\d+\s*ms\b"                                          # 210ms
    r"|\bfrom\s+[\d.]+\s*\w{0,3}\s+to\s+[\d.]+"               # from 800ms to 210ms
    r"|\b(?:increased|decreased|reduced|improved|cut|raised|grew|saved|"
    r"optimi[sz]ed|scaled)\b[^.]{0,60}?\b\d"
    r")", re.I)

_OWNERSHIP_RE = re.compile(
    r"\b(built|designed|implemented|developed|architected|shipped|deployed|led|"
    r"owned|created|migrated|refactored|automated|integrated|scaled|debugged|"
    r"wrote|launched|delivered|maintained)\b", re.I)

_PASSIVE_FILLER_RE = re.compile(
    r"\b(familiar\s+with|exposure\s+to|basic\s+knowledge|good\s+knowledge|"
    r"knowledge\s+of|aware\s+of|interested\s+in|willing\s+to\s+learn|"
    r"hard\s?working|punctual|sincere|dedicated|positive\s+attitude|"
    r"team\s+player|quick\s+learner|can\s+work\s+under\s+pressure)\b", re.I)

_DATE_RANGE_RE = re.compile(
    r"((?:19|20)\d{2})\s*(?:-|–|—|to)\s*((?:19|20)\d{2})", re.I)


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------
def _normalised_fingerprint(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())[:4000]


def check_integrity(resume, jd, pool=None) -> list[Flag]:
    """Flags for one resume. `pool` enables cross-resume duplicate detection."""
    flags: list[Flag] = []
    text = resume.raw_text

    # 1. Seniority mismatch --------------------------------------------------
    ceiling = SENIORITY_CEILING.get(jd.seniority, 40.0)
    if resume.years_experience > ceiling:
        flags.append(Flag(
            code="seniority_mismatch",
            severity="high" if resume.years_experience > ceiling + 2 else "medium",
            title=f"{resume.years_experience:.1f} yrs experience on a {jd.seniority} role",
            detail=(f"This posting is pitched at {jd.seniority} level (ceiling "
                    f"{ceiling:.0f} yrs). Either the candidate is overqualified and "
                    f"likely to decline, or the stated experience is inflated."),
            evidence=resume.experience_source,
        ))

    # 2. Keyword stuffing ----------------------------------------------------
    # The honest signal is NOT "lots of skills in few words" - a good candidate
    # with a tight skills block looks exactly like that. The signal is skills
    # that appear ONLY in a list and never inside described work.
    word_count = len(text.split())
    n_skills = len(resume.skills)
    in_work = sum(1 for s in resume.skills if s.section in ("experience", "projects"))
    backed_ratio = in_work / n_skills if n_skills else 1.0

    if n_skills >= KEYWORD_STUFF_MIN_SKILLS and backed_ratio < 0.12:
        flags.append(Flag(
            code="keyword_stuffing",
            severity="medium",
            title=f"{n_skills} technologies listed, only {in_work} appear in described work",
            detail=("Almost every skill on this resume exists only in a list. None of "
                    "them is attached to a project or a job the candidate describes "
                    "doing. Worth probing in interview."),
            evidence=", ".join(sorted(s.canonical for s in resume.skills)[:14]) + " ...",
        ))
    elif (n_skills >= KEYWORD_STUFF_MIN_SKILLS + 10
          and word_count < n_skills * KEYWORD_STUFF_WORDS_PER_SKILL * 0.4):
        flags.append(Flag(
            code="skill_density", severity="low",
            title=f"{n_skills} technologies in only {word_count} words",
            detail="Unusually dense skill list for the length of the resume.",
            evidence=", ".join(sorted(s.canonical for s in resume.skills)[:14]) + " ...",
        ))

    # A single line that is nothing but a comma-separated technology dump.
    for line in text.splitlines():
        commas = line.count(",")
        if commas >= 14 and len(line.split()) < commas * 3:
            flags.append(Flag(
                code="skill_dump_line",
                severity="low",
                title="One line contains a large undescribed technology dump",
                detail="Common ATS-gaming pattern. Worth confirming in interview.",
                evidence=line.strip()[:200],
            ))
            break

    # 3. Prompt injection ----------------------------------------------------
    m = _INJECTION_RE.search(text)
    if m:
        flags.append(Flag(
            code="prompt_injection",
            severity="high",
            title="Resume contains text addressed to an automated screener",
            detail=("This looks like an attempt to manipulate an AI shortlisting "
                    "system. Our scorer never executes resume text as instructions, "
                    "so the ranking is unaffected - but a human should see this."),
            evidence=text[max(0, m.start() - 40):m.end() + 60].strip()[:220],
        ))

    # 4. Impossible / inconsistent timeline ----------------------------------
    from datetime import date
    this_year = date.today().year
    for dm in _DATE_RANGE_RE.finditer(text):
        start, end = int(dm.group(1)), int(dm.group(2))
        if end < start:
            flags.append(Flag(
                code="timeline_inconsistent", severity="medium",
                title=f"Date range runs backwards ({start}-{end})",
                detail="An end date earlier than its start date. Usually a typo, "
                       "occasionally a fabricated timeline.",
                evidence=dm.group(0)))
            break
        if end > this_year + 1:
            flags.append(Flag(
                code="timeline_future", severity="low",
                title=f"Date range extends to {end}",
                detail="A future end date. Often means 'expected graduation', "
                       "sometimes a typo.",
                evidence=dm.group(0)))
            break

    # Claimed years vs what the dates actually support.
    if resume.experience_source.startswith("stated") and resume.years_experience >= 2:
        from ..parsing.resume import _years_from_date_ranges
        computed = _years_from_date_ranges(text)
        if computed > 0 and resume.years_experience > computed * 2 + 1:
            flags.append(Flag(
                code="experience_unsupported", severity="medium",
                title=f"Claims {resume.years_experience:.1f} yrs but dates support ~{computed:.1f}",
                detail="The stated total does not line up with the employment dates "
                       "listed on the same resume.",
                evidence=resume.experience_source))

    # 5. Unsubstantiated superlatives ---------------------------------------
    supers = {s.group(0).lower() for s in _SUPERLATIVE_RE.finditer(text)}
    if len(supers) >= 3 and not _QUANTIFIED_RE.search(text):
        flags.append(Flag(
            code="unsubstantiated_claims", severity="low",
            title="Strong self-assessment with no measurable results",
            detail="Uses words like " + ", ".join(sorted(supers)[:4]) +
                   " but the resume contains no numbers, metrics or outcomes.",
            evidence=", ".join(sorted(supers)[:6])))

    # 6. Parse quality -------------------------------------------------------
    n_chars = len(text.strip())
    if n_chars < 250:
        flags.append(Flag(
            code="unreadable", severity="high",
            title="Almost no text extracted from this file",
            detail=("The file may be a scanned image, password protected, or in an "
                    "unsupported layout. This candidate is being scored on almost "
                    "nothing - review the original manually."),
            evidence=f"{n_chars} characters extracted via {resume.extraction_method}"))
    elif n_chars < 600:
        flags.append(Flag(
            code="very_short", severity="low",
            title="Unusually short resume",
            detail=("Either a genuinely sparse resume or an extraction that lost "
                    "content. Either way there is little for the engine to score."),
            evidence=f"{n_chars} characters extracted via {resume.extraction_method}"))
    elif resume.warnings:
        flags.append(Flag(
            code="parse_warning", severity="low",
            title="Parser reported warnings on this file",
            detail="Extraction was imperfect; some content may be missing.",
            evidence="; ".join(resume.warnings)[:200]))

    if not resume.skills:
        flags.append(Flag(
            code="no_skills_found", severity="medium",
            title="No recognised skills found",
            detail="Either a genuinely non-technical resume, or the skills section "
                   "did not survive extraction.",
            evidence=""))

    # 7. Timeline analysis (date overlaps, inflated durations, ...) ---------
    try:
        from .timeline import analyse_timeline
        timeline_flags, _ = analyse_timeline(resume, jd)
        flags.extend(timeline_flags)
    except Exception as exc:                        # noqa: BLE001
        flags.append(Flag(
            code="timeline_unavailable", severity="info",
            title="Could not analyse this resume's timeline",
            detail=f"{type(exc).__name__}: {exc}", evidence=""))

    # 8. Duplicate submissions ----------------------------------------------
    if pool:
        mine = _normalised_fingerprint(text)
        for other in pool:
            if other.doc_id == resume.doc_id or not other.raw_text:
                continue
            theirs = _normalised_fingerprint(other.raw_text)
            if not mine or not theirs:
                continue
            shorter, longer = sorted((mine, theirs), key=len)
            if len(shorter) > 300 and shorter[:1500] in longer:
                flags.append(Flag(
                    code="duplicate_resume", severity="medium",
                    title=f"Near-identical to {other.path.name}",
                    detail="Two submissions in this pool share almost all of their "
                           "text. Possible double submission or a shared template.",
                    evidence=other.path.name))
                break

    flags.sort(key=lambda f: SEVERITY_ORDER[f.severity])
    return flags


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------
@dataclass
class Confidence:
    score: float                                   # 0-100
    band: str                                      # High | Moderate | Low | Very low
    components: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 1),
            "band": self.band,
            "components": {k: round(v, 3) for k, v in self.components.items()},
            "reasons": self.reasons,
        }


def _band(score: float) -> str:
    if score >= 70:
        return "High"
    if score >= 50:
        return "Moderate"
    if score >= 30:
        return "Low"
    return "Very low"


def score_confidence(resume, candidate=None) -> Confidence:
    """How well-evidenced is this resume? 0-100.

    This is deliberately INDEPENDENT of the match score. A candidate can be a
    perfect skill match with low confidence (they listed the right words and
    described nothing), or a mediocre match with high confidence (they clearly
    did real work, just not this work). The recruiter needs both numbers.
    """
    text = resume.raw_text
    words = max(1, len(text.split()))
    components: dict[str, float] = {}
    reasons: list[str] = []

    # 1. Quantified outcomes - the single strongest signal of real work.
    quantified = len(set(m.group(0).lower() for m in _QUANTIFIED_RE.finditer(text)))
    components["quantified_results"] = min(1.0, quantified / 5)
    if quantified >= 3:
        reasons.append(f"{quantified} measurable results (numbers, percentages, metrics)")
    elif quantified == 0:
        reasons.append("no measurable results anywhere in the resume")

    # 2. Ownership language vs passive filler.
    owns = len(_OWNERSHIP_RE.findall(text))
    filler = len(_PASSIVE_FILLER_RE.findall(text))
    ratio = owns / (owns + filler) if (owns + filler) else 0.0
    components["ownership_language"] = ratio
    if ratio >= 0.75 and owns >= 4:
        reasons.append(f"{owns} action verbs describing work they did themselves")
    elif filler > owns:
        reasons.append(f"leans on passive phrasing ('familiar with', 'good knowledge') "
                       f"{filler} times vs {owns} action verbs")

    # 3. Do the skills appear in described work, or only in a list?
    doing_sections = {"experience", "projects"}
    in_work = sum(1 for s in resume.skills if s.section in doing_sections)
    total_skills = max(1, len(resume.skills))
    components["skills_backed_by_work"] = min(1.0, in_work / max(3, total_skills * 0.4))
    if in_work >= 3:
        reasons.append(f"{in_work} skills appear inside actual experience or project descriptions")
    elif resume.skills and in_work == 0:
        reasons.append("every skill appears only in a list, never in described work")

    # 4. Section depth - a resume with real projects AND real experience.
    found = {s.name for s in resume.sections}
    depth = len(found & {"experience", "projects", "skills", "education", "certifications"})
    components["section_depth"] = depth / 5
    if "projects" in found and "experience" in found:
        reasons.append("has both work experience and project sections")

    # 5. Verifiable links.
    has_links = bool(resume.links)
    components["verifiable_links"] = 1.0 if has_links else 0.0
    if has_links:
        reasons.append(f"{len(resume.links)} verifiable link(s) (portfolio / repo)")
    else:
        reasons.append("no portfolio or repository link to verify claims against")

    # 6. Substance - enough text to have said something, not so much it is padding.
    if words < 120:
        components["substance"] = 0.15
        reasons.append(f"very short resume ({words} words)")
    elif words < 250:
        components["substance"] = 0.55
    elif words <= 1400:
        components["substance"] = 1.0
    else:
        components["substance"] = 0.75
        reasons.append(f"very long resume ({words} words) - signal is diluted")

    # 7. Parse quality caps everything: we cannot be confident about text we
    #    could not read.
    n_chars = len(text.strip())
    parse_ok = 0.35 if n_chars < 250 else (0.8 if n_chars < 600 else
                                           (0.85 if resume.warnings else 1.0))
    components["parse_quality"] = parse_ok
    if parse_ok < 1.0:
        reasons.append("extraction was imperfect, so this reading is itself uncertain")

    weights = {
        "quantified_results": 0.26,
        "ownership_language": 0.20,
        "skills_backed_by_work": 0.22,
        "section_depth": 0.12,
        "verifiable_links": 0.08,
        "substance": 0.12,
    }
    raw = sum(components[k] * w for k, w in weights.items())
    score = 100 * raw * parse_ok

    return Confidence(score=score, band=_band(score), components=components, reasons=reasons)
