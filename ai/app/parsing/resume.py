"""Turn raw resume text into a structured Resume object."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..matching.skills import SkillHit, get_ontology
from .extract import ExtractedDocument, extract_document
from .sections import Chunk, Section, build_chunks, detect_sections

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3,5}\)?[\s.-]?)?\d{3}[\s.-]?\d{4}\b")
LINK_RE = re.compile(r"(?:https?://|www\.)[^\s,;)<>\]]+", re.I)

_MONTHS = ("jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec")
_DATE_RANGE_RE = re.compile(
    rf"(?:({_MONTHS})[a-z]*\.?\s*,?\s*)?((?:19|20)\d{{2}})\s*(?:-|–|—|to|until|through)\s*"
    rf"(?:(?:({_MONTHS})[a-z]*\.?\s*,?\s*)?((?:19|20)\d{{2}})|(present|current|till date|date|now|ongoing))",
    re.I,
)
_STATED_YEARS_RE = re.compile(
    r"(\d{1,2}(?:\.\d{1,2})?)\s*\+?\s*(?:years?|yrs?)\s*(?:\d+\s*months?\s*)?"
    r"(?:of\s+)?(?:professional\s+|relevant\s+|hands[\s-]?on\s+|total\s+|overall\s+)?"
    r"(?:work\s+|industry\s+|it\s+)?(?:experience|exp\b)",
    re.I,
)
_MONTHS_ONLY_RE = re.compile(r"(\d{1,2})\s*\+?\s*months?\s*(?:of\s+)?(?:experience|exp\b)", re.I)

_DEGREE_LEVELS = [
    (4, r"\b(ph\.?\s?d|doctorate|doctoral)\b"),
    (3, r"\b(m\.?\s?tech|m\.?\s?e\b|m\.?\s?sc|m\.?\s?c\.?\s?a|mba|master'?s?|post\s?graduat)"),
    (2, r"\b(b\.?\s?tech|b\.?\s?e\b|b\.?\s?sc|b\.?\s?c\.?\s?a|b\.?\s?com|bachelor'?s?|under\s?graduat|engineering\s+degree)"),
    (1, r"\b(diploma|polytechnic|12th|higher\s+secondary|intermediate|hsc)\b"),
]
_DEGREE_NAME = {4: "PhD", 3: "Master's", 2: "Bachelor's", 1: "Diploma/12th", 0: "Not stated"}

_STUDENT_MARKERS = re.compile(
    r"\b(fresher|fresh\s+graduate|final\s+year|pre[\s-]?final\s+year|3rd\s+year|third\s+year|"
    r"2nd\s+year|second\s+year|pursuing|currently\s+studying|undergraduate\s+student|"
    r"expected\s+graduation|seeking\s+an?\s+internship)\b", re.I,
)


@dataclass
class Resume:
    doc_id: str
    path: Path
    raw_text: str
    name: str
    email: str | None
    phone: str | None
    links: list[str]
    sections: list[Section]
    chunks: list[Chunk]
    skills: list[SkillHit]
    years_experience: float
    experience_source: str
    education_level: int
    is_student_or_fresher: bool
    extraction_method: str
    warnings: list[str] = field(default_factory=list)

    @property
    def skill_keys(self) -> set[str]:
        return {s.key for s in self.skills}

    @property
    def education_label(self) -> str:
        return _DEGREE_NAME.get(self.education_level, "Not stated")

    def skill(self, key: str) -> SkillHit | None:
        for s in self.skills:
            if s.key == key:
                return s
        return None

    def section_text(self, name: str) -> str:
        return "\n".join(s.text for s in self.sections if s.name == name)

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "file": self.path.name,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "links": self.links,
            "years_experience": self.years_experience,
            "experience_source": self.experience_source,
            "education": self.education_label,
            "is_student_or_fresher": self.is_student_or_fresher,
            "skills": sorted(s.canonical for s in self.skills),
            "sections_found": [s.name for s in self.sections],
            "extraction_method": self.extraction_method,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _guess_name(text: str, email: str | None) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    for line in lines[:14]:
        m = re.match(r"^(?:name|candidate\s*name|full\s*name)\s*[:\-]\s*(.+)$", line, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()[:60]

    # A section header is never a person's name. Without this the parser
    # happily reports candidates called "Technical Skills".
    from .sections import SECTION_SYNONYMS

    header_words = {w for syns in SECTION_SYNONYMS.values() for s in syns for w in s.split()}
    header_words |= {
        "resume", "curriculum", "vitae", "curriculam", "cv", "application",
        "details", "information", "name", "career", "work", "job", "role",
        "technical", "technologies", "tools", "languages", "about", "contact",
    }

    banned = re.compile(
        r"resume|curriculum|vitae|curriculam|^c\.?v\.?$|profile|objective|summary|"
        r"application|contact|mobile|phone|email|address|@|http", re.I)

    for raw_line in lines[:10]:
        # Many resumes put the name and the contact details on ONE line:
        # "Aarav Menon  aarav@x.com | +91 98765 43210". Take the part before
        # the first contact marker and test that.
        line = re.split(r"\s{2,}|\s\|\s|(?=[\w.+-]+@)|(?=\+?\d[\d\s-]{7,})",
                        raw_line, maxsplit=1)[0].strip(" -|,")
        if not line or banned.search(line) or any(ch.isdigit() for ch in line):
            continue
        words = line.split()
        if not (1 <= len(words) <= 5) or len(line) > 45:
            continue
        if any(w.strip(":,.").lower() in header_words for w in words):
            continue
        alpha = [w for w in words if re.fullmatch(r"[A-Za-z.'\-]+", w)]
        if len(alpha) == len(words):
            return re.sub(r"\s+", " ", line.title() if line.isupper() else line)[:60]

    # Derive from the email only if it looks like a real personal address.
    # "dummy.email@example.com" produced twenty candidates all called
    # "Dummy Email", which then looked like one person twenty times over.
    from ..matching.dedupe import is_placeholder_email

    if email and not is_placeholder_email(email):
        local = re.split(r"[._\-0-9]+", email.split("@")[0])
        guess = " ".join(p.capitalize() for p in local if len(p) > 1)
        if guess:
            return guess

    # Last resort: the first substantive line, even if it has digits in it.
    # A label like "Candidate 16 - Blockchain Developer" is not a name, but it
    # IS a distinct identifier, which beats collapsing everyone into one row.
    for line in lines[:4]:
        if banned.search(line) or len(line) > 60:
            continue
        if sum(ch.isalpha() for ch in line) >= 4:
            return re.sub(r"\s+", " ", line).strip(" -|,")[:60]
    return "Unknown Candidate"


def _years_from_date_ranges(text: str) -> float:
    """Sum non-overlapping employment date ranges, in years."""
    this_year = date.today().year
    spans: list[tuple[float, float]] = []
    month_idx = {m: i for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

    for m in _DATE_RANGE_RE.finditer(text):
        sm, sy, em, ey, present = m.groups()
        try:
            start = int(sy) + (month_idx.get((sm or "jan")[:3].lower(), 1) - 1) / 12
        except (TypeError, ValueError):
            continue
        if present:
            end = this_year + date.today().month / 12
        elif ey:
            end = int(ey) + (month_idx.get((em or "dec")[:3].lower(), 12)) / 12
        else:
            continue
        if 1980 <= start <= this_year + 1 and start < end <= this_year + 1.5:
            spans.append((start, end))

    if not spans:
        return 0.0

    spans.sort()
    merged: list[list[float]] = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= merged[-1][1] + 0.1:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return round(sum(e - s for s, e in merged), 2)


def _extract_experience(text: str, sections: list[Section]) -> tuple[float, str]:
    """Prefer an explicit claim ('1.7 years of experience'); fall back to dates."""
    stated = [float(m.group(1)) for m in _STATED_YEARS_RE.finditer(text)]
    stated = [y for y in stated if 0 < y <= 45]
    if stated:
        return max(stated), "stated in resume text"

    months = [int(m.group(1)) for m in _MONTHS_ONLY_RE.finditer(text)]
    months = [mo for mo in months if 0 < mo <= 120]
    if months:
        return round(max(months) / 12, 2), "stated in months"

    exp_text = "\n".join(s.text for s in sections if s.name in ("experience", "projects"))
    computed = _years_from_date_ranges(exp_text or text)
    if computed > 0:
        return computed, "computed from employment date ranges"

    return 0.0, "no experience signal found (treated as fresher)"


def _education_level(text: str) -> int:
    for level, pattern in _DEGREE_LEVELS:
        if re.search(pattern, text, re.I):
            return level
    return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_resume(source: str | Path | ExtractedDocument, doc_id: str | None = None) -> Resume:
    doc = source if isinstance(source, ExtractedDocument) else extract_document(source)
    text = doc.text

    sections = detect_sections(text)
    chunks = build_chunks(sections)
    skills = get_ontology().extract_with_sections(sections)

    email_m = EMAIL_RE.search(text)
    email = email_m.group(0) if email_m else None

    phone = None
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits) <= 13:
            phone = m.group(0).strip()
            break

    years, source_desc = _extract_experience(text, sections)
    fresher = bool(_STUDENT_MARKERS.search(text)) or years == 0.0

    return Resume(
        # Full filename, not the stem: a pool routinely contains the same resume
        # exported as .pdf, .docx, .txt and .xml. Sharing a doc_id across those
        # also made them share the semantic matcher's embedding cache, so three
        # of the four were scored against the wrong vectors.
        doc_id=doc_id or doc.path.name,
        path=doc.path,
        raw_text=text,
        name=_guess_name(text, email),
        email=email,
        phone=phone,
        links=list(dict.fromkeys(LINK_RE.findall(text)))[:5],
        sections=sections,
        chunks=chunks,
        skills=skills,
        years_experience=years,
        experience_source=source_desc,
        education_level=_education_level(text),
        is_student_or_fresher=fresher,
        extraction_method=doc.method,
        warnings=list(doc.warnings),
    )


def parse_resume_folder(folder: str | Path) -> list[Resume]:
    from .extract import extract_folder
    return [parse_resume(doc) for doc in extract_folder(folder)]
