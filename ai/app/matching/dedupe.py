"""Identity resolution: which of these files are the same person?

Real applicant pools contain the same candidate more than once - they applied
twice, the placement cell exported the same resume as PDF and DOCX, someone
re-submitted after fixing a typo. A shortlist that shows one person in positions
1, 3, 4 and 7 is worse than useless to a recruiter: it looks like four strong
candidates when there is one.

WHY THIS IS NOT JUST "GROUP BY EMAIL"

In the pack we were given, `dummy.email@example.com` appears on twenty
different resumes belonging to twenty different people. Grouping on email alone
would have merged all twenty into one candidate and silently deleted nineteen
people from the shortlist. That is the single worst failure mode this module
could have, so email is only trusted when it looks like a real personal address.

THE RULES, IN ORDER OF STRENGTH

  1. Same non-placeholder email                       -> same person
  2. Same normalised name AND same phone              -> same person
  3. Same normalised name AND very similar content    -> same person
  4. Near-identical content (>= 92% shared shingles)  -> same person

Anything weaker stays separate. The cost of wrongly splitting one person into
two rows is a mild annoyance; the cost of wrongly merging two people is that one
of them vanishes from the shortlist. The rules are tuned accordingly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Addresses that are obviously not a specific person.
_PLACEHOLDER_EMAIL = re.compile(
    r"(^|@)(dummy|sample|test|example|placeholder|noreply|no-reply|yourname|"
    r"firstname|lastname|abc|xyz|email|your|candidate|applicant)\b"
    r"|@(example|test|sample|domain|email|mail)\.(com|org|net|in)$",
    re.I,
)

_NAME_NOISE = re.compile(r"\b(mr|mrs|ms|dr|prof|resume|cv|curriculum|vitae)\b", re.I)

# Names the parser produced because it could not find a real one. Matching on
# these would merge unrelated people, so the name-based rules skip them.
_UNRELIABLE_NAME = re.compile(
    r"^(unknown candidate|dummy|candidate\s*\d|applicant\s*\d|resume|cv|"
    r"n/?a|test user|your name|first ?last)\b", re.I)


def name_is_reliable(name: str | None) -> bool:
    if not name or len(name.strip()) < 4:
        return False
    if _UNRELIABLE_NAME.match(name.strip()):
        return False
    # A "name" containing a digit is a label, not a person.
    return not any(ch.isdigit() for ch in name)


def is_placeholder_email(email: str | None) -> bool:
    if not email:
        return True
    return bool(_PLACEHOLDER_EMAIL.search(email.strip().lower()))


def normalise_name(name: str | None) -> str:
    if not name:
        return ""
    n = _NAME_NOISE.sub(" ", name.lower())
    n = re.sub(r"[^a-z ]+", " ", n)
    return " ".join(sorted(n.split()))          # order-insensitive: "Rao Kavya" == "Kavya Rao"


def normalise_phone(phone: str | None) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    return digits[-10:] if len(digits) >= 10 else ""


def _shingles(text: str, k: int = 5) -> set[str]:
    words = re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split()
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


CONTENT_SAME_PERSON = 0.92       # near-identical: same doc, different export
CONTENT_WITH_NAME = 0.70         # same TRUSTED name + broadly the same content

# Templated resumes ("Candidate 16 - Blockchain Developer", generic filler) can
# be 75% identical to each other while describing different people. Content
# similarity alone therefore has to clear a high bar, and the name rule only
# applies when the parser actually found a name it trusts.


@dataclass
class IdentityGroup:
    group_id: str
    primary: object                       # the Resume we keep
    members: list = field(default_factory=list)
    reason: str = ""

    @property
    def duplicates(self) -> list:
        return [r for r in self.members if r.doc_id != self.primary.doc_id]

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "candidate": self.primary.name,
            "primary_file": self.primary.path.name,
            "duplicate_files": [r.path.name for r in self.duplicates],
            "copies": len(self.members),
            "reason": self.reason,
        }


def _quality(resume) -> tuple:
    """Which copy of a duplicate set should we keep?

    Prefer the one the parser got the most out of: no warnings, most text,
    most skills recognised. Format is the tiebreak - structured XML and DOCX
    keep their section headers, a PDF export often does not.
    """
    fmt_rank = {"xml": 5, "python-docx": 4, "pymupdf": 3, "pdfplumber": 3,
                "plaintext": 2, "pypdf": 2}.get(resume.extraction_method, 1)
    return (
        0 if resume.warnings else 1,
        len(resume.skills),
        len(resume.raw_text),
        fmt_rank,
        resume.path.name,                 # deterministic final tiebreak
    )


def group_identities(resumes: list) -> list[IdentityGroup]:
    """Cluster a pool into one group per real person."""
    n = len(resumes)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int, why: str) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri
            reasons[ri] = reasons.get(ri) or why

    reasons: dict[int, str] = {}

    emails = [None if is_placeholder_email(r.email) else r.email.strip().lower()
              for r in resumes]
    names = [normalise_name(r.name) if name_is_reliable(r.name) else "" for r in resumes]
    phones = [normalise_phone(r.phone) for r in resumes]
    shingles = [_shingles(r.raw_text) for r in resumes]

    # Rule 1: real, shared email.
    by_email: dict[str, list[int]] = {}
    for i, e in enumerate(emails):
        if e:
            by_email.setdefault(e, []).append(i)
    for e, idxs in by_email.items():
        for j in idxs[1:]:
            union(idxs[0], j, f"same email ({e})")

    # Rules 2-4 need pairwise comparison, but only within plausible buckets so
    # this stays fast on a large pool: same name, or same phone.
    buckets: dict[str, list[int]] = {}
    for i in range(n):
        if names[i]:
            buckets.setdefault(f"n:{names[i]}", []).append(i)
        if phones[i]:
            buckets.setdefault(f"p:{phones[i]}", []).append(i)

    for key, idxs in buckets.items():
        if len(idxs) < 2:
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                if find(i) == find(j):
                    continue
                same_name = names[i] and names[i] == names[j]
                same_phone = phones[i] and phones[i] == phones[j]
                if same_name and same_phone:
                    union(i, j, "same name and phone number")
                    continue
                sim = _jaccard(shingles[i], shingles[j])
                if same_name and sim >= CONTENT_WITH_NAME and sim < CONTENT_SAME_PERSON:
                    union(i, j, f"same name, {sim:.0%} identical content")
                elif sim >= CONTENT_SAME_PERSON:
                    union(i, j, f"{sim:.0%} identical content")

    # Rule 4 across the whole pool would be O(n^2); restrict it to files whose
    # basenames already suggest the same source document.
    def stem_key(r) -> str:
        return re.sub(r"[^a-z0-9]+", "", r.path.stem.lower())

    by_stem: dict[str, list[int]] = {}
    for i, r in enumerate(resumes):
        by_stem.setdefault(stem_key(r), []).append(i)
    for idxs in by_stem.values():
        for j in idxs[1:]:
            if find(idxs[0]) != find(j):
                sim = _jaccard(shingles[idxs[0]], shingles[j])
                if sim >= CONTENT_SAME_PERSON:
                    union(idxs[0], j, f"same filename, {sim:.0%} identical content")

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    groups: list[IdentityGroup] = []
    for root, idxs in clusters.items():
        members = [resumes[i] for i in idxs]
        primary = max(members, key=_quality)
        groups.append(IdentityGroup(
            group_id=primary.doc_id,
            primary=primary,
            members=members,
            reason=reasons.get(root, "") if len(members) > 1 else "",
        ))

    groups.sort(key=lambda g: g.primary.doc_id)
    return groups


def dedupe_report(resumes: list) -> dict:
    """Summary for the UI / CLI."""
    groups = group_identities(resumes)
    multi = [g for g in groups if len(g.members) > 1]
    return {
        "files": len(resumes),
        "unique_candidates": len(groups),
        "duplicate_groups": len(multi),
        "files_removed_by_collapsing": sum(len(g.duplicates) for g in multi),
        "groups": [g.to_dict() for g in multi],
    }
