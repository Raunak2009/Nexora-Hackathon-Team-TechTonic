"""Turn a Job Description into a structured requirement set.

The JD is the query side of the problem. We pull out:
  * required skills   - explicitly demanded ("must have", "required", "strong")
  * preferred skills  - nice-to-haves ("a plus", "bonus", "familiarity with")
  * requirement lines - free-text bullets, kept verbatim so the semantic matcher
                        can compare meaning rather than words
  * minimum experience, role title, seniority

Required vs preferred is decided by TWO signals: the heading a bullet sits under
and modal language inside the bullet itself. Bullet-level language wins, because
JDs routinely bury "experience with Docker is a plus" inside a Requirements list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..matching.skills import SkillHit, get_ontology
from .extract import ExtractedDocument, extract_document
from .sections import _looks_like_header

REQUIRED_HEADINGS = re.compile(
    r"\b(requirements?|required\s+skills?|must[\s-]?haves?|qualifications?|"
    r"minimum\s+qualifications?|what\s+we(?:'re|\s+are)\s+looking\s+for|who\s+you\s+are|"
    r"skills?\s+(?:&|and)\s+(?:experience|qualifications?)|essential|eligibility|"
    r"technical\s+requirements?|key\s+skills?|candidate\s+profile)\b", re.I)

PREFERRED_HEADINGS = re.compile(
    r"\b(nice[\s-]?to[\s-]?haves?|preferred(?:\s+qualifications?|\s+skills?)?|bonus|"
    r"good\s+to\s+have|desirable|plus(?:es)?|optional|we(?:'d|\s+would)\s+love|"
    r"additional\s+skills?|advantageous)\b", re.I)

RESPONSIBILITY_HEADINGS = re.compile(
    r"\b(responsibilities|what\s+you(?:'ll|\s+will)\s+do|duties|"
    r"role\s+overview|day\s+to\s+day|key\s+responsibilities|the\s+role)\b", re.I)

# Headings whose bullets are company marketing, not candidate requirements.
# Everything under these is skipped so we never "match" a resume against
# "we offer free snacks".
NOISE_HEADINGS = re.compile(
    r"\b(about\s+(?:us|the\s+role|the\s+company|technova)|job\s+description|"
    r"the\s+opportunity|what\s+we\s+offer|benefits?|perks?|compensation|salary|"
    r"how\s+to\s+apply|application\s+process|location|duration|stipend|"
    r"why\s+join|our\s+(?:culture|values|mission)|equal\s+opportunity|disclaimer|"
    r"company\s+(?:overview|profile))\b", re.I)

OTHER_HEADINGS = re.compile(
    RESPONSIBILITY_HEADINGS.pattern + "|" + NOISE_HEADINGS.pattern, re.I)

# A bullet only becomes a Requirement if it names a skill or reads like an ask.
REQUIREMENTY = re.compile(
    r"\b(experience|knowledge|understanding|proficien|familiar|exposure|skills?|"
    r"ability|able\s+to|comfortable|degree|pursuing|graduat|must|should|"
    r"required?|expected|build|design|implement|develop|write|maintain|"
    r"work\s+with|participate|debug|test|deploy|manage|hands[\s-]?on)\b", re.I)

PREFERRED_INLINE = re.compile(
    r"\b(is\s+a\s+plus|are\s+a\s+plus|a\s+plus\b|nice\s+to\s+have|good\s+to\s+have|"
    r"preferred|bonus\s+points?|would\s+be\s+(?:a\s+)?(?:plus|advantage|great)|"
    r"familiarity\s+with|exposure\s+to|awareness\s+of|basic\s+(?:understanding|knowledge)\s+of|"
    r"desirable|optional|advantageous|ideally|willing(?:ness)?\s+to\s+learn)\b", re.I)

REQUIRED_INLINE = re.compile(
    r"\b(must\s+have|must\s+be|required|require[sd]?\b|strong\s+(?:knowledge|command|grasp|"
    r"understanding|experience|proficiency)|proficien(?:t|cy)\s+in|solid\s+(?:understanding|"
    r"knowledge|grasp)|hands[\s-]?on\s+experience|demonstrated|essential|mandatory|"
    r"should\s+have|expected\s+to)\b", re.I)

MIN_EXP_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)"
    r"(?:\s+of)?(?:\s+\w+){0,3}?\s*experience", re.I)

SENIORITY_RE = [
    ("intern", r"\b(intern|internship|trainee|apprentice)\b"),
    ("junior", r"\b(junior|entry[\s-]?level|fresher|graduate|jr\.?|associate|0[\s-]?2\s+years)\b"),
    ("mid", r"\b(mid[\s-]?level|intermediate|software\s+engineer\s+ii)\b"),
    ("senior", r"\b(senior|sr\.?|lead|principal|staff|architect|head\s+of)\b"),
]


@dataclass
class Requirement:
    """One atomic ask from the JD."""
    text: str
    kind: str                 # "required" | "preferred"
    heading: str
    skills: list[str] = field(default_factory=list)   # ontology keys named here


@dataclass
class JobDescription:
    path: Path | None
    raw_text: str
    title: str
    seniority: str
    min_years: float
    max_years: float | None
    required_skills: list[SkillHit]
    preferred_skills: list[SkillHit]
    requirements: list[Requirement]
    responsibilities: list[str]

    @property
    def required_keys(self) -> list[str]:
        return [s.key for s in self.required_skills]

    @property
    def preferred_keys(self) -> list[str]:
        return [s.key for s in self.preferred_skills]

    @property
    def requirement_texts(self) -> list[str]:
        return [r.text for r in self.requirements] or [self.raw_text[:2000]]

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "seniority": self.seniority,
            "min_years": self.min_years,
            "max_years": self.max_years,
            "required_skills": [s.canonical for s in self.required_skills],
            "preferred_skills": [s.canonical for s in self.preferred_skills],
            "requirement_count": len(self.requirements),
            "responsibilities": self.responsibilities[:10],
        }


def _guess_title(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    role_word = re.compile(
        r"\b(engineer|developer|intern|analyst|scientist|designer|architect|manager|"
        r"administrator|consultant|specialist|lead|programmer|tester)\b", re.I)
    for line in lines[:18]:
        m = re.match(r"^(?:job\s+title|position|role|designation)\s*[:\-]\s*(.+)$", line, re.I)
        if m:
            return m.group(1).strip()[:90]
    for line in lines[:12]:
        if role_word.search(line) and len(line) <= 90 and not line.endswith('.'):
            return re.sub(r"\s{2,}", " ", line).strip(" :-")[:90]
    return lines[0][:90] if lines else "Untitled Role"


def _seniority(text: str, min_years: float) -> str:
    head = text[:1200]
    for label, pattern in SENIORITY_RE:
        if re.search(pattern, head, re.I):
            return label
    for label, pattern in SENIORITY_RE:
        if re.search(pattern, text, re.I):
            return label
    if min_years >= 6:
        return "senior"
    if min_years >= 3:
        return "mid"
    return "junior"


def _experience_range(text: str) -> tuple[float, float | None]:
    best: tuple[float, float | None] | None = None
    for m in MIN_EXP_RE.finditer(text):
        lo = float(m.group(1))
        hi = float(m.group(2)) if m.group(2) else None
        if lo > 40:
            continue
        if best is None or lo < best[0]:
            best = (lo, hi)
    return best if best else (0.0, None)


_KNOWN_HEADING = re.compile(
    "|".join((REQUIRED_HEADINGS.pattern, PREFERRED_HEADINGS.pattern, OTHER_HEADINGS.pattern)),
    re.I,
)

# A line that starts with a bullet marker is a LIST ITEM, never a heading.
# Without this, a terse JD written as
#     Required:
#     - Node.js
#     - MongoDB
# loses every skill: "Node.js" is short and title-cased, so the shape heuristic
# reads it as a section header and it never becomes a requirement.
_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•●▪·–—]|\d+[.)])\s+")


def _iter_bullets(text: str):
    """Yield (heading, line) pairs, tracking the most recent heading.

    A line is treated as a heading if it either looks like one structurally
    (short, title/upper case, no sentence punctuation) OR is a short line whose
    whole content is a heading phrase we recognise - JD exports often lose the
    formatting that would have made it obvious.
    """
    heading = ""
    for raw in text.splitlines():
        is_list_item = bool(_BULLET_PREFIX.match(raw))
        line = raw.strip(" -*•●▪·\t")
        line = re.sub(r"^\d+[.)]\s+", "", line)
        if not line:
            continue

        stripped = line.strip(" :")
        is_short = len(stripped.split()) <= 6 and len(stripped) <= 55
        if (not is_list_item and is_short
                and (_looks_like_header(raw) or _KNOWN_HEADING.search(stripped))):
            heading = stripped
            continue

        yield heading, line


def parse_jd(source: str | Path | ExtractedDocument) -> JobDescription:
    if isinstance(source, ExtractedDocument):
        doc, text, path = source, source.text, source.path
    elif isinstance(source, (str, Path)) and Path(str(source)).exists():
        doc = extract_document(source)
        text, path = doc.text, doc.path
    else:  # a raw JD string pasted from the frontend
        from .extract import normalize_text
        text, path = normalize_text(str(source)), None

    ontology = get_ontology()
    min_years, max_years = _experience_range(text)

    requirements: list[Requirement] = []
    responsibilities: list[str] = []
    required_evidence: dict[str, SkillHit] = {}
    preferred_evidence: dict[str, SkillHit] = {}

    for heading, line in _iter_bullets(text):
        # Company marketing is not a requirement. Skip it entirely so nothing in
        # the pipeline ever matches a resume against "we offer mentorship".
        if NOISE_HEADINGS.search(heading):
            continue

        is_resp = bool(RESPONSIBILITY_HEADINGS.search(heading))
        head_pref = bool(PREFERRED_HEADINGS.search(heading))
        head_req = bool(REQUIRED_HEADINGS.search(heading))

        # Bullet-level language overrides the heading.
        if PREFERRED_INLINE.search(line):
            kind = "preferred"
        elif REQUIRED_INLINE.search(line):
            kind = "required"
        elif head_pref:
            kind = "preferred"
        elif head_req:
            kind = "required"
        elif is_resp:
            kind = "required"   # responsibilities still describe needed ability
        else:
            kind = "required"

        hits = ontology.extract(line, section="skills")
        if is_resp and len(line.split()) > 3:
            responsibilities.append(line)

        # Keep a line as a Requirement only if it names a skill or reads like an
        # ask. This keeps the semantic matcher comparing resumes against real
        # demands instead of against filler prose.
        if hits or (len(line.split()) >= 4 and REQUIREMENTY.search(line)):
            requirements.append(Requirement(
                text=line, kind=kind, heading=heading or "(no heading)",
                skills=[h.key for h in hits],
            ))

        bucket = preferred_evidence if kind == "preferred" else required_evidence
        for h in hits:
            bucket.setdefault(h.key, h)

    # A skill demanded anywhere as required stays required.
    for key in list(preferred_evidence):
        if key in required_evidence:
            preferred_evidence.pop(key)

    # Fallback: an unstructured JD blob with no bullets we could split.
    if not required_evidence and not preferred_evidence:
        for h in ontology.extract(text, section="skills"):
            required_evidence[h.key] = h

    return JobDescription(
        path=path,
        raw_text=text,
        title=_guess_title(text),
        seniority=_seniority(text, min_years),
        min_years=min_years,
        max_years=max_years,
        required_skills=list(required_evidence.values()),
        preferred_skills=list(preferred_evidence.values()),
        requirements=requirements,
        responsibilities=responsibilities,
    )
