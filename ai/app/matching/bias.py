"""Bonus feature: flag bias and over-narrow phrasing in the JD itself.

This audits the *job description*, not the candidates. A JD that says "young,
energetic graduate from a tier-1 college" will quietly shrink the qualified pool
before any ranking happens, and a recruiter usually has no idea they wrote it.

Pure rule-based and fully auditable - every flag names the phrase it fired on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class BiasFlag:
    category: str
    severity: str
    phrase: str
    context: str
    why: str
    suggestion: str

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity,
            "phrase": self.phrase,
            "context": self.context,
            "why": self.why,
            "suggestion": self.suggestion,
        }


# (category, severity, regex, why, suggestion)
RULES: list[tuple[str, str, str, str, str]] = [
    ("age", "high",
     r"\b(young|youthful|energetic\s+young|recent\s+grad(?:uate)?s?\s+only|"
     r"under\s+\d{2}\s*(?:years|yrs)?\s*(?:of\s*age|old)|digital\s+native|"
     r"born\s+(?:after|in)\s+(?:19|20)\d{2}|age\s*(?:limit|below|under|max)\s*[:\-]?\s*\d{2}|"
     r"fresh\s+blood|youngsters?)\b",
     "Screens on age rather than ability.",
     "Describe the skill level you need instead of an age or graduation year."),

    ("gender", "high",
     r"\b(he/she\s+must|salesman|salesmen|manpower|chairman|craftsman|"
     r"guys\b|men\s+only|women\s+only|male\s+candidates?|female\s+candidates?|"
     r"preferably\s+(?:male|female)|strong\s+man)\b",
     "Gendered wording narrows who applies, even when unintended.",
     "Use neutral wording: 'they', 'salesperson', 'staffing', 'chairperson'."),

    ("marital/family", "high",
     r"\b(unmarried|married|single\s+candidates?|no\s+family\s+commitments?|"
     r"not\s+planning\s+(?:a\s+)?(?:family|children)|marital\s+status)\b",
     "Marital or family status has no bearing on job performance.",
     "Remove entirely."),

    ("appearance", "medium",
     r"\b(good[\s-]?looking|attractive|presentable\s+(?:appearance|personality)|"
     r"pleasing\s+personality|well[\s-]?groomed|smart\s+looking|height\s*[:\-]?\s*\d)",
     "Appearance requirements are unrelated to most roles and deter applicants.",
     "Drop, or state the concrete client-facing behaviour you need."),

    ("nationality/language", "medium",
     r"\b(native\s+(?:english|hindi)\s+speaker|mother\s+tongue|"
     r"only\s+(?:indian|local)\s+candidates?|must\s+be\s+a\s+citizen|"
     r"no\s+visa\s+sponsorship\s+under\s+any)\b",
     "'Native speaker' and nationality filters exclude fluent non-native candidates.",
     "Specify the proficiency level actually needed, e.g. 'professional working English'."),

    ("ability", "medium",
     r"\b(no\s+(?:health\s+issues|disabilit(?:y|ies))|physically\s+fit\s+candidates?\s+only|"
     r"able[\s-]bodied|must\s+be\s+able\s+to\s+(?:stand|lift)\s+(?!.*with\s+accommodation))\b",
     "Ability requirements not essential to the role exclude disabled candidates.",
     "State only genuinely essential physical requirements, and offer accommodations."),

    ("pedigree", "high",
     r"\b(tier[\s-]?(?:1|one|i)\s+(?:colleges?|institutes?|universit(?:y|ies))|"
     r"iits?|nits?|bits\s+pilani|"
     r"ivy\s+league|premier\s+institutes?\s+only|top\s+(?:tier|ranked)\s+"
     r"(?:college|university|institute)s?\s+only|reputed\s+college\s+only)\b",
     "Institution filters correlate with background, not capability, and shrink the pool sharply.",
     "Screen on demonstrated skills and projects instead of where someone studied."),

    ("academic-cutoff", "medium",
     r"\b(cgpa|gpa|percentage|aggregate)\s*(?:of\s*)?(?:>=?|above|minimum|min\.?|not\s+less\s+than)?\s*"
     r"\d{1,2}(?:\.\d{1,2})?\s*%?\b|no\s+(?:backlogs?|arrears?|standing\s+arrears?)",
     "Hard academic cutoffs exclude strong self-taught and late-blooming candidates.",
     "Treat academics as one signal among several rather than a gate."),

    ("career-gap", "high",
     r"\b(no\s+(?:career\s+)?gaps?|continuous\s+employment|"
     r"unexplained\s+gaps?\s+(?:will\s+be\s+)?(?:not\s+)?(?:accepted|rejected)|"
     r"must\s+be\s+currently\s+employed)\b",
     "Gap filters disproportionately screen out carers, people who were ill, and career changers.",
     "Ask about recent relevant work instead of continuity."),

    ("over-narrow-version", "low",
     r"\b(?:react|angular|node(?:\.js)?|python|java|php|django|spring)\s*"
     r"(?:v(?:ersion)?\s*)?\d{1,2}(?:\.\d{1,2}){1,2}\b",
     "Pinning an exact minor version rules out people who know the technology well.",
     "Name the technology, not the patch version."),

    ("over-narrow-exact-years", "medium",
     r"\b(?:exactly|precisely)\s+\d{1,2}\s*(?:years?|yrs?)|"
     r"\b\d{1,2}\s*(?:years?|yrs?)\s*(?:experience\s*)?(?:only|exactly)\b",
     "An exact-years window rejects people a few months either side for no reason.",
     "Use a minimum ('2+ years') or describe the scope of work you expect them to own."),

    ("commitment", "low",
     r"\b(work\s+hard,?\s+play\s+hard|rockstar|ninja|guru|wizard|"
     r"willing\s+to\s+work\s+(?:long|extended)\s+hours|"
     r"24/7\s+availability|no\s+work[\s-]life\s+balance|"
     r"like\s+a\s+family|thrive\s+under\s+(?:extreme\s+)?pressure)\b",
     "Hustle framing signals poor boundaries and deters carers and disabled applicants.",
     "Describe the actual pace and on-call expectations concretely."),
]

_COMPILED = [(c, s, re.compile(p, re.I), w, g) for c, s, p, w, g in RULES]


def _context(text: str, start: int, end: int, width: int = 60) -> str:
    lo, hi = max(0, start - width), min(len(text), end + width)
    return ("..." if lo else "") + re.sub(r"\s+", " ", text[lo:hi]).strip() + ("..." if hi < len(text) else "")


def audit_jd(jd) -> dict:
    text = jd.raw_text
    flags: list[BiasFlag] = []
    seen: set[tuple[str, str]] = set()

    for category, severity, pattern, why, suggestion in _COMPILED:
        for m in pattern.finditer(text):
            phrase = re.sub(r"\s+", " ", m.group(0)).strip()
            if (category, phrase.lower()) in seen:
                continue
            seen.add((category, phrase.lower()))
            flags.append(BiasFlag(category, severity, phrase,
                                  _context(text, m.start(), m.end()), why, suggestion))

    # Structural checks, not phrase matches.
    n_required = len(jd.required_skills)
    if jd.seniority in ("intern", "junior") and n_required >= 10:
        flags.append(BiasFlag(
            "over-narrow-stack", "medium",
            f"{n_required} required skills for a {jd.seniority} role",
            ", ".join(s.canonical for s in jd.required_skills[:12]),
            "A long must-have list on a junior role filters out capable people who "
            "simply have not touched one item on it yet.",
            "Split the list into 3-5 true must-haves and move the rest to 'nice to have'.",
        ))

    if jd.seniority in ("intern", "junior") and jd.min_years >= 2:
        flags.append(BiasFlag(
            "experience-inflation", "medium",
            f"{jd.min_years:.0f}+ years required on a {jd.seniority} role",
            jd.title,
            "Asking for multiple years of professional experience on an intern/junior "
            "posting is a contradiction that suppresses applications.",
            "Drop the years requirement or reclassify the role's seniority.",
        ))

    if not jd.preferred_skills and n_required >= 6:
        flags.append(BiasFlag(
            "no-flexibility", "low",
            "every listed skill is framed as mandatory",
            f"{n_required} required, 0 preferred",
            "With no nice-to-haves, borderline-but-strong candidates self-select out.",
            "Mark the genuinely optional skills as preferred.",
        ))

    flags.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.category))

    return {
        "flag_count": len(flags),
        "high_severity": sum(1 for f in flags if f.severity == "high"),
        "flags": [f.to_dict() for f in flags],
        "summary": _summary(flags, jd),
    }


def _summary(flags: list[BiasFlag], jd) -> str:
    if not flags:
        return (f"No bias or over-narrow phrasing detected in '{jd.title}'. "
                f"{len(jd.required_skills)} required and {len(jd.preferred_skills)} "
                f"preferred skills, which is a reasonable spread.")
    high = [f for f in flags if f.severity == "high"]
    cats = sorted({f.category for f in flags})
    lead = (f"{len(flags)} potential issue(s) found in '{jd.title}' across: "
            f"{', '.join(cats)}.")
    if high:
        lead += (" Highest priority: " +
                 "; ".join(f"\"{f.phrase}\" ({f.category})" for f in high[:3]) + ".")
    return lead
