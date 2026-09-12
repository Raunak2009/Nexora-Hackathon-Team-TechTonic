"""Timeline reconstruction and date-based integrity checks.

Pulls every dated entry out of a resume - jobs, internships, projects, degrees -
places them on a real calendar, and looks for things that should not be true at
the same time.

WHAT THIS CATCHES

  date_overlap          Two full-time roles running at once. Sometimes genuine
                        (part-time alongside study, contract work), which is why
                        it is a flag for a human rather than a score penalty.
  overlap_cluster       Three or more entries live in the same month. Much
                        harder to explain than a single overlap.
  duration_inflation    Months claimed across entries far exceed the calendar
                        span they actually cover - the classic symptom of
                        stretched dates.
  experience_precedes_education
                        Professional experience dated well before the degree
                        started. Usually a typo in a year; occasionally not.
  suspiciously_uniform  Every single entry is exactly the same length, to the
                        month. Real careers are lumpy; generated ones are not.
  future_dated          An end date beyond next year that is not marked
                        "expected" or "present".

WHAT THIS DELIBERATELY DOES NOT CATCH

  Employment gaps. A gap is not evidence of anything - gap screening filters out
  carers, people who were ill, and career changers, and our own JD bias audit
  flags employers who do it. Flagging candidates for the same thing the audit
  criticises employers for would be incoherent.

Everything returns the lines it fired on, so the UI can show the evidence rather
than asking anyone to trust a label.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))
_PRESENT = r"present|current|till\s*date|to\s*date|now|ongoing|date"

# "Jun 2024 - Jul 2024", "2022 – 2026", "03/2025 - 08/2025", "June 2024 - Present"
_RANGE_RE = re.compile(
    rf"(?:(?P<sm>{_MONTH_ALT})\.?\s*,?\s*)?(?P<sy>(?:19|20)\d{{2}})"
    rf"\s*(?:-|–|—|to|until|through|until)\s*"
    rf"(?:(?:(?P<em>{_MONTH_ALT})\.?\s*,?\s*)?(?P<ey>(?:19|20)\d{{2}})|(?P<present>{_PRESENT}))",
    re.I,
)
_NUMERIC_RANGE_RE = re.compile(
    rf"(?P<sm>0?[1-9]|1[0-2])[/-](?P<sy>(?:19|20)\d{{2}})"
    rf"\s*(?:-|–|—|to)\s*"
    rf"(?:(?P<em>0?[1-9]|1[0-2])[/-](?P<ey>(?:19|20)\d{{2}})|(?P<present>{_PRESENT}))",
    re.I,
)

_EXPECTED_RE = re.compile(r"\b(expected|anticipated|graduating|to\s+be\s+completed)\b", re.I)

# Sections whose dates describe PAID WORK. Overlapping projects or courses are
# completely normal; overlapping jobs are the interesting case.
WORK_SECTIONS = {"experience"}
STUDY_SECTIONS = {"education"}
SIDE_SECTIONS = {"projects", "certifications", "achievements"}


@dataclass
class TimelineEntry:
    start: float                 # decimal year, e.g. 2024.42
    end: float
    label: str                   # the line it came from
    section: str
    kind: str                    # work | study | side | other
    is_present: bool = False
    is_expected: bool = False

    @property
    def months(self) -> float:
        return max(0.0, (self.end - self.start) * 12)

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "start_label": _fmt(self.start),
            "end_label": "Present" if self.is_present else _fmt(self.end),
            "months": round(self.months, 1),
            "kind": self.kind,
            "section": self.section,
            "label": self.label[:160],
            "is_present": self.is_present,
            "is_expected": self.is_expected,
        }


def _fmt(decimal_year: float) -> str:
    year = int(decimal_year)
    month = min(12, max(1, int(round((decimal_year - year) * 12)) + 1))
    return f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][month-1]} {year}"


def _decimal(year: int, month: int | None) -> float:
    return year + ((month or 1) - 1) / 12


def _kind_for(section: str) -> str:
    if section in WORK_SECTIONS:
        return "work"
    if section in STUDY_SECTIONS:
        return "study"
    if section in SIDE_SECTIONS:
        return "side"
    return "other"


def extract_timeline(resume) -> list[TimelineEntry]:
    """Every dated entry in the resume, placed on a calendar.

    Walks section by section so each entry knows whether it is a job, a degree
    or a side project - which is what makes the overlap check meaningful.
    """
    today = date.today()
    now = _decimal(today.year, today.month)
    entries: list[TimelineEntry] = []

    for section in resume.sections:
        kind = _kind_for(section.name)
        for line in section.text.splitlines():
            if not line.strip():
                continue
            expected = bool(_EXPECTED_RE.search(line))

            for regex, numeric in ((_RANGE_RE, False), (_NUMERIC_RANGE_RE, True)):
                for m in regex.finditer(line):
                    try:
                        sy = int(m.group("sy"))
                        sm = m.group("sm")
                        start_month = int(sm) if numeric and sm else (
                            MONTHS.get(str(sm).lower()) if sm else None)
                        start = _decimal(sy, start_month)
                    except (TypeError, ValueError):
                        continue

                    is_present = bool(m.group("present"))
                    if is_present:
                        end = now
                    else:
                        try:
                            ey = int(m.group("ey"))
                            em = m.group("em")
                            end_month = int(em) if numeric and em else (
                                MONTHS.get(str(em).lower()) if em else 12)
                            end = _decimal(ey, end_month)
                        except (TypeError, ValueError):
                            continue

                    if not (1980 <= start <= now + 8):
                        continue
                    if end < start:
                        end = start          # handled as its own flag elsewhere

                    entries.append(TimelineEntry(
                        start=start, end=end, label=line.strip(), section=section.name,
                        kind=kind, is_present=is_present, is_expected=expected,
                    ))
                if entries and numeric is False and regex.search(line):
                    break                    # don't double-count the same line

    entries.sort(key=lambda e: (e.start, e.end))
    return entries


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
OVERLAP_TOLERANCE_MONTHS = 1.0     # a month of handover is normal, not suspicious
MIN_ENTRY_MONTHS = 1.0             # ignore single-month blips


def _overlap_months(a: TimelineEntry, b: TimelineEntry) -> float:
    return max(0.0, (min(a.end, b.end) - max(a.start, b.start)) * 12)


def analyse_timeline(resume, jd=None) -> tuple[list, dict]:
    """Returns (flags, timeline_payload).

    `flags` are integrity.Flag objects. `timeline_payload` is everything the UI
    needs to draw a Gantt-style timeline of the candidate's history, with the
    overlapping pairs marked.
    """
    from .integrity import Flag

    entries = extract_timeline(resume)
    flags: list[Flag] = []
    today = date.today()
    now = _decimal(today.year, today.month)

    work = [e for e in entries if e.kind == "work" and e.months >= MIN_ENTRY_MONTHS]
    overlaps: list[dict] = []

    # 1. Pairwise overlap between WORK entries -------------------------------
    for i in range(len(work)):
        for j in range(i + 1, len(work)):
            a, b = work[i], work[j]
            months = _overlap_months(a, b)
            if months <= OVERLAP_TOLERANCE_MONTHS:
                continue
            # One entry fully inside another is a stronger signal than a
            # partial overlap at a job change.
            contained = (a.start <= b.start and a.end >= b.end) or \
                        (b.start <= a.start and b.end >= a.end)
            overlaps.append({
                "a": a.to_dict(), "b": b.to_dict(),
                "overlap_months": round(months, 1),
                "fully_contained": contained,
            })

    if overlaps:
        worst = max(overlaps, key=lambda o: o["overlap_months"])
        severity = "medium" if worst["overlap_months"] >= 3 or worst["fully_contained"] else "low"
        flags.append(Flag(
            code="date_overlap",
            severity=severity,
            title=(f"{len(overlaps)} overlapping role(s) - "
                   f"up to {worst['overlap_months']:.0f} months at once"),
            detail=("Two roles on this resume run at the same time. That can be "
                    "genuine - part-time work alongside study, contracting, a "
                    "notice period - but it is worth one question in the "
                    "interview rather than an assumption either way."),
            evidence=(f"\"{worst['a']['label'][:70]}\" ({worst['a']['start_label']}"
                      f"-{worst['a']['end_label']}) overlaps "
                      f"\"{worst['b']['label'][:70]}\" ({worst['b']['start_label']}"
                      f"-{worst['b']['end_label']})"),
        ))

    # 2. Three or more entries alive in the same month -----------------------
    if len(work) >= 3:
        months_axis = sorted({round(e.start, 2) for e in work} |
                             {round(e.end, 2) for e in work})
        worst_month, worst_count = None, 0
        for point in months_axis:
            live = [e for e in work if e.start <= point < e.end]
            if len(live) > worst_count:
                worst_month, worst_count = point, len(live)
        if worst_count >= 3:
            flags.append(Flag(
                code="overlap_cluster", severity="medium",
                title=f"{worst_count} roles running simultaneously around {_fmt(worst_month)}",
                detail=("Three or more concurrent roles is considerably harder to "
                        "explain than a single overlap. Check the dates directly."),
                evidence="; ".join(e.label[:50] for e in work
                                   if e.start <= worst_month < e.end)[:220],
            ))

    # 3. Claimed duration vs calendar span -----------------------------------
    if len(work) >= 2:
        claimed = sum(e.months for e in work)
        span = (max(e.end for e in work) - min(e.start for e in work)) * 12
        if span > 0 and claimed > span * 1.5 + 6:
            flags.append(Flag(
                code="duration_inflation", severity="medium",
                title=(f"{claimed:.0f} months of roles claimed inside a "
                       f"{span:.0f}-month window"),
                detail=("The individual role durations add up to far more time than "
                        "the calendar span they sit in. Usually stretched start or "
                        "end dates."),
                evidence=f"{len(work)} roles between {_fmt(min(e.start for e in work))} "
                         f"and {_fmt(max(e.end for e in work))}",
            ))

    # 4. Work that predates study -------------------------------------------
    study = [e for e in entries if e.kind == "study"]
    if work and study:
        study_start = min(e.start for e in study)
        early = [e for e in work if e.start < study_start - 2]
        if early:
            e = min(early, key=lambda x: x.start)
            flags.append(Flag(
                code="experience_precedes_education", severity="low",
                title=f"Professional role dated {_fmt(e.start)}, "
                      f"over 2 years before studies began ({_fmt(study_start)})",
                detail=("Often a mistyped year. Occasionally it means the resume's "
                        "timeline was assembled rather than lived."),
                evidence=e.label[:200],
            ))

    # 5. Every entry exactly the same length ---------------------------------
    if len(work) >= 3:
        lengths = {round(e.months) for e in work}
        if len(lengths) == 1 and work[0].months >= 2:
            flags.append(Flag(
                code="suspiciously_uniform", severity="low",
                title=f"All {len(work)} roles are exactly {work[0].months:.0f} months long",
                detail=("Real careers are lumpy. Identical durations across every "
                        "entry is a pattern worth a second look."),
                evidence="; ".join(e.label[:45] for e in work)[:200],
            ))

    # 6. Future-dated, and not marked as expected ---------------------------
    future = [e for e in entries
              if e.end > now + 1.05 and not e.is_expected and not e.is_present]
    if future:
        e = max(future, key=lambda x: x.end)
        flags.append(Flag(
            code="future_dated", severity="low",
            title=f"Entry ends {_fmt(e.end)}, in the future",
            detail="Not labelled 'expected' or 'present', so it reads as a "
                   "completed period that has not happened yet.",
            evidence=e.label[:200],
        ))

    payload = {
        "entries": [e.to_dict() for e in entries],
        "work_entries": len(work),
        "overlaps": overlaps,
        "total_work_months": round(sum(e.months for e in work), 1),
        "calendar_span_months": (
            round((max(e.end for e in work) - min(e.start for e in work)) * 12, 1)
            if work else 0.0
        ),
        "earliest": _fmt(min(e.start for e in entries)) if entries else None,
        "latest": _fmt(max(e.end for e in entries)) if entries else None,
    }
    return flags, payload
