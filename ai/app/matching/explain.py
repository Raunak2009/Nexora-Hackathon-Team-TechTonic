"""Natural-language explanations, generated from the score trace - no LLM.

Every sentence here is assembled from values the matcher actually computed, so
an explanation can never claim a skill the candidate does not have. That is the
difference between an explanation and a plausible-sounding paragraph.
"""

from __future__ import annotations


def _listify(items: list[str], limit: int = 6, empty: str = "none") -> str:
    items = [i for i in items if i]
    if not items:
        return empty
    shown = items[:limit]
    extra = len(items) - len(shown)
    if len(shown) == 1:
        body = shown[0]
    else:
        body = ", ".join(shown[:-1]) + " and " + shown[-1]
    return body + (f" (+{extra} more)" if extra else "")


def _verdict(score: float, missing_required: int) -> str:
    if score >= 72 and missing_required == 0:
        return "Strong fit"
    if score >= 60:
        return "Good fit"
    if score >= 45:
        return "Partial fit"
    if score >= 30:
        return "Weak fit"
    return "Poor fit"


def explain_candidate(candidate, jd, detail: str = "full") -> str:
    r = candidate.resume
    exact = [m.canonical for m in candidate.required_matches if m.status == "exact"]
    related = [m for m in candidate.required_matches if m.status == "related"]
    semantic = [m for m in candidate.required_matches if m.status == "semantic"]
    missing = [m.canonical for m in candidate.missing_required]

    # Only skills the candidate ACTUALLY NAMES are reported as "brings".
    # Inferred credit is reported separately and hedged - an explanation that
    # says "also brings Docker" about someone who never wrote Docker is worse
    # than no explanation at all.
    pref_exact = [m.canonical for m in candidate.preferred_matches if m.status == "exact"]
    pref_inferred = [m.canonical for m in candidate.preferred_matches
                     if m.status in ("related", "semantic")]

    verdict = _verdict(candidate.score, len(missing))
    lines: list[str] = []

    lines.append(
        f"#{candidate.rank} {r.name} - {candidate.score:.1f}/100 ({verdict} for "
        f"{jd.title})."
    )

    # 1. Direct skill evidence
    if exact:
        lines.append(f"Directly matches {len(exact)} of {len(candidate.required_matches)} "
                     f"required skills: {_listify(exact)}.")
    else:
        lines.append("Does not name any of the required skills directly.")

    # 2. Ontology / semantic partial credit
    if related:
        parts = [f"{m.canonical} (via {m.reason.split('related ')[-1]})" for m in related[:3]]
        lines.append(f"Partial credit on {_listify(parts, 3)} - adjacent technology, "
                     f"not the exact one asked for.")
    if semantic:
        m = semantic[0]
        lines.append(f"Implied {m.canonical} without naming it: \"{m.evidence[:110]}\".")

    # 3. Best semantic evidence - the "meaning not words" part
    best = [m for m in candidate.semantic_result.best_matches if m.similarity > 0.3][:2]
    if best:
        b = best[0]
        lines.append(
            f"Closest match to the JD's ask \"{b.requirement[:80]}\" is their line "
            f"\"{b.evidence[:100]}\" (similarity {b.similarity:.2f})."
        )

    # 4. Gaps - stated plainly, this is what a recruiter needs
    if missing:
        hard_missing = [m.canonical for m in candidate.missing_required if m.is_hard]
        soft_missing = [m.canonical for m in candidate.missing_required if not m.is_hard]
        if hard_missing:
            lines.append(f"Missing / no evidence for: {_listify(hard_missing)}.")
        if soft_missing:
            lines.append(f"Missing but lower-weight: {_listify(soft_missing, 4)}.")
    else:
        lines.append("No required skill is entirely unevidenced.")

    if pref_exact:
        lines.append(f"Also names preferred skills: {_listify(pref_exact, 5)}.")
    if pref_inferred:
        lines.append(f"Weaker, inferred-only signal on {_listify(pref_inferred, 4)} "
                     f"- not named outright, treat as unconfirmed.")

    # 5. Experience
    lines.append(candidate.experience_note)

    if detail == "full":
        c = candidate.contributions
        breakdown = ", ".join(
            f"{k.replace('_', ' ')} {v:+.1f}" for k, v in
            sorted(c.items(), key=lambda kv: -abs(kv[1]))
        )
        lines.append(f"Score breakdown (points out of 100): {breakdown}.")

    if candidate.flags:
        lines.append("Caution: " + "; ".join(candidate.flags) + ".")

    return " ".join(lines)


def explain_top_n(candidates, jd, n: int = 3) -> list[dict]:
    out = []
    for c in candidates[:n]:
        c.explanation = explain_candidate(c, jd)
        out.append({
            "rank": c.rank,
            "candidate": c.resume.name,
            "file": c.resume.path.name,
            "score": c.score,
            "matched_skills": [m.canonical for m in c.matched_required],
            "missing_skills": [m.canonical for m in c.missing_required],
            "explanation": c.explanation,
        })
    return out


def compare_candidates(a, b, jd) -> str:
    """Answer 'Why is Candidate X ranked above Candidate Y?' from the trace."""
    if a.score < b.score:
        a, b = b, a

    a_skills = {m.canonical for m in a.matched_required}
    b_skills = {m.canonical for m in b.matched_required}
    only_a, only_b = sorted(a_skills - b_skills), sorted(b_skills - a_skills)

    diffs = []
    for field in ("required_skills", "semantic", "lexical", "preferred_skills", "experience"):
        delta = a.contributions.get(field, 0) - b.contributions.get(field, 0)
        if abs(delta) >= 0.5:
            diffs.append((field, delta))
    diffs.sort(key=lambda kv: -abs(kv[1]))

    parts = [
        f"{a.resume.name} ranks #{a.rank} at {a.score:.1f} and {b.resume.name} ranks "
        f"#{b.rank} at {b.score:.1f} - a gap of {a.score - b.score:.1f} points."
    ]

    if diffs:
        driver, delta = diffs[0]
        parts.append(
            f"The biggest driver is {driver.replace('_', ' ')}, worth "
            f"{delta:+.1f} points to {a.resume.name}."
        )
        if len(diffs) > 1:
            parts.append("Then " + ", ".join(
                f"{d.replace('_', ' ')} {v:+.1f}" for d, v in diffs[1:4]) + ".")

    if only_a:
        parts.append(f"{a.resume.name} covers {_listify(only_a)} which "
                     f"{b.resume.name} does not.")
    if only_b:
        parts.append(f"{b.resume.name} does bring {_listify(only_b)}, but it was not "
                     f"enough to close the gap.")

    a_miss = [m.canonical for m in a.missing_required]
    b_miss = [m.canonical for m in b.missing_required]
    if len(b_miss) > len(a_miss):
        parts.append(f"{b.resume.name} is missing {len(b_miss)} required skills "
                     f"({_listify(b_miss, 4)}) against {a.resume.name}'s {len(a_miss)}.")

    if abs(a.resume.years_experience - b.resume.years_experience) >= 0.5:
        parts.append(
            f"Experience: {a.resume.years_experience:.1f} yrs vs "
            f"{b.resume.years_experience:.1f} yrs."
        )

    return " ".join(parts)
