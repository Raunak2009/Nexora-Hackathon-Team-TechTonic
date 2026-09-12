"""Section detection and chunking for resumes.

Resumes have no schema. One writes "TECHNICAL SKILLS", the next "Skill Set",
the next "Core Competencies", the next nothing at all. We detect sections with a
synonym map plus shape heuristics (short line, title/upper case, no sentence
punctuation), and we always succeed: unlabelled text lands in an "other"
section rather than being dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import MAX_CHUNK_WORDS, MIN_CHUNK_WORDS

SECTION_SYNONYMS: dict[str, list[str]] = {
    "summary": [
        "summary", "profile", "professional summary", "career objective", "objective",
        "profile summary", "about me", "career summary", "executive summary",
        "personal profile", "career profile", "professional profile", "overview",
    ],
    "skills": [
        "skills", "technical skills", "technical skill", "skill set", "skillset",
        "core competencies", "competencies", "technical expertise", "technical proficiency",
        "technologies", "tech stack", "areas of expertise", "key skills", "it skills",
        "computer skills", "technical summary", "software skills", "tools and technologies",
        "programming skills", "expertise", "technical knowledge", "proficiencies",
    ],
    "experience": [
        "experience", "work experience", "professional experience", "employment",
        "employment history", "work history", "career history", "professional background",
        "industry experience", "relevant experience", "internship", "internships",
        "internship experience", "work", "positions held", "organizational experience",
    ],
    "projects": [
        "projects", "project", "academic projects", "personal projects", "key projects",
        "project undertaken", "projects undertaken", "project details", "project experience",
        "major projects", "minor project", "project work", "selected projects",
        "project profile", "notable projects",
    ],
    "education": [
        "education", "academic", "academics", "educational qualification",
        "educational qualifications", "academic qualification", "academic qualifications",
        "educational details", "academic details", "qualification", "qualifications",
        "education and training", "academic background", "scholastics",
    ],
    "certifications": [
        "certifications", "certification", "certificates", "courses", "training",
        "trainings", "licenses", "professional development", "workshops",
        "certifications and training", "online courses",
    ],
    "achievements": [
        "achievements", "accomplishments", "awards", "honors", "honours",
        "awards and achievements", "achievements and awards", "extra curricular activities",
        "extracurricular activities", "co-curricular activities", "activities",
        "positions of responsibility", "publications",
    ],
    "personal": [
        "personal details", "personal information", "personal profile details",
        "declaration", "references", "hobbies", "interest", "interests",
        "interest & hobbies", "hobbies and interests", "languages known",
        "personal attributes", "strengths",
    ],
}

# Reverse lookup, longest-first so "technical skills" wins over "skills".
_HEADER_LOOKUP: list[tuple[str, str]] = sorted(
    ((syn, sec) for sec, syns in SECTION_SYNONYMS.items() for syn in syns),
    key=lambda kv: -len(kv[0]),
)

# Sections that describe what the candidate can actually DO. Used to weight
# evidence: a skill named under "Projects" is stronger than one under "Hobbies".
EVIDENCE_WEIGHT: dict[str, float] = {
    # Experience and projects outrank a bare skills list: "built X with React"
    # is stronger evidence of React than "React" appearing in a comma list, and
    # it is also the better line to quote back to the recruiter.
    "experience": 1.0,
    "projects": 0.97,
    "skills": 0.92,
    "summary": 0.85,
    "certifications": 0.8,
    "education": 0.6,
    "achievements": 0.5,
    "other": 0.7,
    "personal": 0.25,
}


@dataclass
class Section:
    name: str
    header: str
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


@dataclass
class Chunk:
    """A short piece of the resume we can embed and cite as evidence."""
    text: str
    section: str
    line_no: int

    @property
    def weight(self) -> float:
        return EVIDENCE_WEIGHT.get(self.section, 0.7)


def _clean_header_candidate(line: str) -> str:
    s = line.strip()
    s = re.sub(r"^[^\w]+|[^\w]+$", "", s)          # strip ---, ***, :, etc.
    s = re.sub(r"\s*[:\-–]\s*$", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _looks_like_header(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 60:
        return False
    words = s.split()
    if len(words) > 6:
        return False
    if s.endswith(('.', ',', ';')):
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(c.isupper() for c in letters) / len(letters)
    title_case = all(w[:1].isupper() for w in words if w[:1].isalpha())
    return upper_ratio > 0.7 or s.endswith(':') or title_case


def detect_sections(text: str) -> list[Section]:
    lines = text.splitlines()
    sections: list[Section] = []
    current = Section(name="other", header="")

    for line in lines:
        candidate = _clean_header_candidate(line)
        matched: str | None = None

        if candidate and _looks_like_header(line):
            for synonym, section_name in _HEADER_LOOKUP:
                if candidate == synonym:
                    matched = section_name
                    break
            if matched is None:
                for synonym, section_name in _HEADER_LOOKUP:
                    if len(synonym) >= 6 and synonym in candidate and len(candidate) <= len(synonym) + 18:
                        matched = section_name
                        break

        if matched:
            if current.lines or current.header:
                sections.append(current)
            current = Section(name=matched, header=line.strip())
        else:
            current.lines.append(line)

    if current.lines or current.header:
        sections.append(current)

    # Merge duplicates (resumes often have "Projects" twice).
    merged: dict[str, Section] = {}
    order: list[str] = []
    for sec in sections:
        if sec.name in merged:
            merged[sec.name].lines.extend([""] + sec.lines)
        else:
            merged[sec.name] = sec
            order.append(sec.name)
    return [merged[name] for name in order]


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def build_chunks(sections: list[Section]) -> list[Chunk]:
    """Split into embeddable units, roughly one bullet or sentence each."""
    chunks: list[Chunk] = []
    line_no = 0

    for section in sections:
        # Skills sections are often "Languages: Java, Python | DB: MySQL" walls.
        # Splitting them on separators gives tight, quotable evidence lines.
        splitter = re.compile(r"[|;\n]") if section.name == "skills" else re.compile(r"\n")

        for raw in splitter.split(section.text):
            line_no += 1
            piece = raw.strip(" -*•\t")
            if not piece:
                continue

            candidates = [piece]
            if len(piece.split()) > MAX_CHUNK_WORDS:
                candidates = _SENT_SPLIT.split(piece)

            for cand in candidates:
                cand = cand.strip()
                words = cand.split()
                if len(words) < MIN_CHUNK_WORDS:
                    # Keep very short lines only if they look like a skill list.
                    if not (section.name == "skills" and len(cand) > 2):
                        continue
                if len(words) > MAX_CHUNK_WORDS:
                    for i in range(0, len(words), MAX_CHUNK_WORDS):
                        sub = " ".join(words[i:i + MAX_CHUNK_WORDS])
                        chunks.append(Chunk(sub, section.name, line_no))
                    continue
                chunks.append(Chunk(cand, section.name, line_no))

    return chunks
