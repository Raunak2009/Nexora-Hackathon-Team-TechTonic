"""Parsing layer - same public API as the original, backed by the engine.

WHAT CHANGED AND WHY
--------------------
The original version worked, but had four things that cost real accuracy on the
kind of resumes we will actually be handed:

1. `if _name_ == "_main_":` (single underscores) in every file. Python never
   matches that, so `python main.py` silently did nothing. Almost certainly a
   copy-paste artifact - markdown eats double underscores as italics - but it
   was in the file, so: fixed everywhere.

2. The JD bullet regex was `re.compile(r"^[\\-\\\\u2022]\\s(.+)")`. Inside a raw
   string `\\\\u2022` is a literal backslash-u-2-0-2-2, not a bullet character,
   and putting it in a character class made it match the characters `\\ u 2 0`.
   So real bullets ("- Node.js", "* React") parsed inconsistently and any
   line starting with "u" was treated as a bullet. Handled properly now.

3. Section detection only fired on an exact match against six alias lists.
   Real resumes write "TECHNICAL SKILLS:", "Skill Set", "Core Competencies",
   "Areas of Expertise" - and about a third of them use no headers at all. The
   engine's detector adds shape heuristics (short line, title/upper case, no
   sentence punctuation) and always succeeds, dropping unlabelled text into an
   "other" bucket rather than losing it.

4. `required_skills` held whole bullet LINES ("Solid understanding of
   JavaScript and modern front-end development"), which then got fuzzy-matched
   as a single string against the resume. Nothing matched. This version returns
   canonical skill names ("JavaScript", "React", "Node.js") resolved through a
   119-node ontology, so "reactjs", "React.js" and "React Hooks" all land on
   the same skill.

WHAT DID NOT CHANGE
-------------------
Every function keeps its name, arguments and return shape. `parse_resume(path)`
still returns a dict of sections plus `_raw` and `_filename`. `parse_jd(text)`
still returns `required_skills`, `nice_to_have_skills`, `min_years_experience`
and `_raw`. Anything already written against this module keeps working.
"""

from __future__ import annotations

import os
from typing import Dict, List

from engine_bridge import (
    ExtractedDocument,
    engine_parse_jd,
    engine_parse_resume,
    extract_document,
    normalize_text,
)

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".doc", ".txt", ".md", ".rtf")


# ---------------------------------------------------------------------------
# 1. Raw text extraction
# ---------------------------------------------------------------------------
def extract_text(path: str) -> str:
    """Extract text from a resume or JD file.

    Now also handles legacy `.doc` (Word 97-2003) and `.rtf`, and tries three
    different PDF readers before giving up - the sample pack the organisers
    sent was full of `.doc`, and pdfplumber alone returns nothing on a
    two-column PDF layout.

    Never raises on a readable-but-awkward file: a file it truly cannot read
    comes back as "" and the caller decides, instead of one bad file killing
    the whole batch.
    """
    doc = extract_document(path)
    return doc.text


def extract_text_from_pdf(path: str) -> str:
    """Kept for backwards compatibility."""
    return extract_text(path)


def extract_text_from_docx(path: str) -> str:
    """Kept for backwards compatibility.

    Also reads DOCX TABLES now, not just paragraphs - a lot of resumes put the
    entire skills matrix inside a table, and the original skipped all of it.
    """
    return extract_text(path)


def clean_text(text: str) -> str:
    """Normalise whitespace, ligatures, smart quotes and bullet characters.

    Additionally un-spaces letter-spaced PDF headers ("S K I L L S" -> "SKILLS")
    and rejoins words that PDF extraction split across lines.
    """
    return normalize_text(text)


# ---------------------------------------------------------------------------
# 2. Resume section splitting
# ---------------------------------------------------------------------------
# Kept so existing imports of this name still resolve. The engine's map is far
# larger (60+ aliases across 8 sections); this mirrors the original six.
SECTION_ALIASES = {
    "skills": ["skills", "technical skills", "core competencies", "technologies"],
    "experience": ["experience", "work experience", "professional experience",
                   "employment history", "internships"],
    "education": ["education", "academic background", "qualifications"],
    "projects": ["projects", "personal projects", "academic projects"],
    "certifications": ["certifications", "certificates", "licenses"],
    "summary": ["summary", "objective", "profile", "about me"],
}


def split_into_sections(text: str) -> Dict[str, str]:
    """Split resume text into {section_name: content}.

    Same contract as before. Unlabelled content lands under "other" (the engine's
    name for what the original called "general"); both keys are present in the
    result so either spelling works downstream.
    """
    from app.parsing.sections import detect_sections

    sections = detect_sections(normalize_text(text))
    out = {s.name: s.text for s in sections if s.text.strip()}
    if "other" in out and "general" not in out:
        out["general"] = out["other"]
    return out


def parse_resume(path: str) -> Dict[str, object]:
    """File -> cleaned text -> sections. Same return shape as the original.

    Adds structured fields the engine extracted anyway, which the API and the
    integrity checks use:

        _engine    the full Resume object (skills, chunks, sections)
        _skills    canonical skill names found, e.g. ["React", "Node.js"]
        _years     years of experience, from a stated claim or from date ranges
        _name      the candidate's name (never a section header)
        _email     / _phone / _links
        _warnings  anything that went wrong reading the file
    """
    resume = engine_parse_resume(path)

    out: Dict[str, object] = {s.name: s.text for s in resume.sections if s.text.strip()}
    if "other" in out and "general" not in out:
        out["general"] = out["other"]

    out["_raw"] = resume.raw_text
    out["_filename"] = os.path.basename(str(path))
    out["_engine"] = resume
    out["_skills"] = sorted(s.canonical for s in resume.skills)
    out["_years"] = resume.years_experience
    out["_name"] = resume.name
    out["_email"] = resume.email
    out["_phone"] = resume.phone
    out["_links"] = resume.links
    out["_education"] = resume.education_label
    out["_warnings"] = resume.warnings
    return out


def parse_resume_text(text: str, filename: str = "pasted.txt") -> Dict[str, object]:
    """Same as parse_resume but for text you already have (API uploads)."""
    from pathlib import Path

    doc = ExtractedDocument(path=Path(filename), text=normalize_text(text), method="inline")
    resume = engine_parse_resume(doc, doc_id=filename)

    out: Dict[str, object] = {s.name: s.text for s in resume.sections if s.text.strip()}
    out["_raw"] = resume.raw_text
    out["_filename"] = filename
    out["_engine"] = resume
    out["_skills"] = sorted(s.canonical for s in resume.skills)
    out["_years"] = resume.years_experience
    out["_name"] = resume.name
    return out


# ---------------------------------------------------------------------------
# 3. JD parsing
# ---------------------------------------------------------------------------
REQUIRED_MARKERS = ["required", "must have", "must-have", "requirements", "you must"]
PREFERRED_MARKERS = ["preferred", "nice to have", "nice-to-have", "bonus", "good to have"]


def parse_jd(jd_text: str) -> Dict[str, object]:
    """Parse a JD into required / preferred skills and minimum experience.

    Two behaviour changes worth knowing about, both of which matter for scoring:

    * Required vs preferred is now decided by the heading a bullet sits under
      AND by the language inside the bullet itself, with the bullet winning.
      JDs constantly bury "experience with Docker is a plus" inside a
      Requirements list, and the original would have called that required.

    * Company marketing is dropped. Bullets under "What We Offer", "About Us",
      "Benefits", "How to Apply" never become requirements, so nothing in the
      pipeline ever tries to match a resume against "we offer mentorship".

    Extra keys are added; none are removed.
    """
    jd = engine_parse_jd(jd_text)
    return {
        # original keys, same meaning
        "required_skills": [s.canonical for s in jd.required_skills],
        "nice_to_have_skills": [s.canonical for s in jd.preferred_skills],
        "min_years_experience": jd.min_years if jd.min_years > 0 else None,
        "_raw": jd.raw_text,
        # added
        "_engine": jd,
        "title": jd.title,
        "seniority": jd.seniority,
        "max_years_experience": jd.max_years,
        "requirements": [
            {"text": r.text, "kind": r.kind, "heading": r.heading, "skills": r.skills}
            for r in jd.requirements
        ],
        "responsibilities": jd.responsibilities,
    }


def parse_jd_file(path: str) -> Dict[str, object]:
    """Read a JD from a .pdf / .docx / .txt file and parse it."""
    return parse_jd(extract_text(path))


# ---------------------------------------------------------------------------
if __name__ == "__main__":
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
    parsed = parse_jd(sample_jd)
    print("required :", parsed["required_skills"])
    print("preferred:", parsed["nice_to_have_skills"])
    print("min years:", parsed["min_years_experience"])
    print("seniority:", parsed["seniority"])
