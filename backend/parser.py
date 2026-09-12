"""
Parsing layer for the Smart Shortlisting Engine.

Responsibilities:
1. Extract raw text from resume files (PDF / DOCX / TXT).
2. Split resume text into rough sections (skills, experience, education, projects).
3. Parse a Job Description into required skills, nice-to-have skills, and
   minimum years of experience.

This is intentionally heuristic (regex + keyword based), not ML-based —
the goal here is clean, structured input for the matching layer that
comes next. Garbage in here means garbage out downstream, so section
splitting has multiple fallback strategies.
"""

import os
import re
from typing import Dict, List

import pdfplumber
import docx


# ---------------------------------------------------------------------------
# 1. Raw text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(path: str) -> str:
    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def extract_text_from_docx(path: str) -> str:
    document = docx.Document(path)
    return "\n".join(p.text for p in document.paragraphs if p.text.strip())


def extract_text(path: str) -> str:
    """Dispatch to the right extractor based on file extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(path)
    elif ext == ".docx":
        return extract_text_from_docx(path)
    elif ext == ".txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def clean_text(text: str) -> str:
    """Normalize whitespace, drop weird control characters."""
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# 2. Resume section splitting
# ---------------------------------------------------------------------------

# Common section header variants, mapped to a canonical section name.
SECTION_ALIASES = {
    "skills": ["skills", "technical skills", "core competencies", "technologies"],
    "experience": ["experience", "work experience", "professional experience",
                   "employment history", "internships"],
    "education": ["education", "academic background", "qualifications"],
    "projects": ["projects", "personal projects", "academic projects"],
    "certifications": ["certifications", "certificates", "licenses"],
    "summary": ["summary", "objective", "profile", "about me"],
}

# Build a flat lookup: header text -> canonical section name
_HEADER_TO_SECTION = {
    alias: canonical
    for canonical, aliases in SECTION_ALIASES.items()
    for alias in aliases
}

# A line is treated as a section header if it's short, and matches (loosely)
# one of the known aliases — case-insensitive, punctuation-stripped.
def _normalize_header(line: str) -> str:
    return re.sub(r"[^a-z ]", "", line.lower()).strip()


def split_into_sections(text: str) -> Dict[str, str]:
    """
    Split resume text into {section_name: content}.
    Falls back to putting everything under 'general' if no headers
    are detected, so downstream code never has to handle a missing key
    for resumes with no clear structure.
    """
    lines = text.split("\n")
    sections: Dict[str, List[str]] = {}
    current_section = "general"
    sections[current_section] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        normalized = _normalize_header(stripped)
        # Header heuristic: short line (<=4 words) that matches a known alias
        if normalized in _HEADER_TO_SECTION and len(stripped.split()) <= 4:
            current_section = _HEADER_TO_SECTION[normalized]
            sections.setdefault(current_section, [])
            continue

        sections[current_section].append(stripped)

    return {k: "\n".join(v) for k, v in sections.items() if v}


def parse_resume(path: str) -> Dict[str, str]:
    """Full pipeline: file -> cleaned text -> sections."""
    raw = extract_text(path)
    cleaned = clean_text(raw)
    sections = split_into_sections(cleaned)
    sections["_raw"] = cleaned  # keep full text too, useful for embeddings later
    sections["_filename"] = os.path.basename(path)
    return sections


# ---------------------------------------------------------------------------
# 3. JD parsing
# ---------------------------------------------------------------------------

REQUIRED_MARKERS = ["required", "must have", "must-have", "requirements", "you must"]
PREFERRED_MARKERS = ["preferred", "nice to have", "nice-to-have", "bonus", "good to have"]

def parse_jd(jd_text: str) -> Dict[str, object]:
    """
    Very heuristic JD parser: bullet lines under a 'required'-style heading
    go into required_skills, bullet lines under a 'preferred'-style heading
    go into nice_to_have_skills. Also pulls a minimum years-of-experience
    number if mentioned.
    """
    cleaned = clean_text(jd_text)
    lines = [l.strip() for l in cleaned.split("\n") if l.strip()]

    required: List[str] = []
    preferred: List[str] = []
    mode = None  # None | "required" | "preferred"

    bullet_pattern = re.compile(r"^[\-\\u2022]\s(.+)")

    for line in lines:
        lower = line.lower()

        if any(m in lower for m in REQUIRED_MARKERS):
            mode = "required"
            continue
        if any(m in lower for m in PREFERRED_MARKERS):
            mode = "preferred"
            continue

        bullet_match = bullet_pattern.match(line)
        if bullet_match:
            item = bullet_match.group(1).strip()
            # A bullet that's really an experience requirement (e.g.
            # "2+ years of experience") isn't a skill — skip it here,
            # the years_match regex below picks it up separately.
            if re.search(r"\d+\+?\s*(?:years|yrs)", item.lower()):
                continue
            if mode:
                (required if mode == "required" else preferred).append(item)
            else:
                # Unlabeled bullet list — treat as required by default,
                # since most JDs lead with must-haves.
                required.append(item)

    years_match = re.search(r"(\d+)\+?\s*(?:years|yrs)", cleaned.lower())
    min_years = int(years_match.group(1)) if years_match else None

    return {
        "required_skills": required,
        "nice_to_have_skills": preferred,
        "min_years_experience": min_years,
        "_raw": cleaned,
    }


# ---------------------------------------------------------------------------
# Quick manual test — run: python parser.py
# ---------------------------------------------------------------------------

if _name_ == "_main_":
    sample_resume = """
    John Doe

    Summary
    Backend-focused developer with a passion for scalable systems.

    Skills
    Python, Node.js, Express, MongoDB, Docker

    Experience
    Backend Intern, Acme Corp
    Built REST APIs with Express and MongoDB, deployed via Docker.

    Education
    B.Tech Computer Science, 2026
    """

    sample_jd = """
    Backend Developer

    Required:
    - Node.js
    - MongoDB
    - 2+ years of experience

    Preferred:
    - Docker
    - AWS
    """

    print("--- Resume sections ---")
    for k, v in split_into_sections(clean_text(sample_resume)).items():
        print(f"[{k}]\n{v}\n")

    print("--- JD parsed ---")
    print(parse_jd(sample_jd))