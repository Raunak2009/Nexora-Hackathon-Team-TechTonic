"""Ranking layer - same public API as the original, backed by the engine.

No LLM anywhere. Explanations are assembled from the matched/missing skill lists
and the score trace the matcher already computed, so every sentence is traceable
back to a real number and a real line in the resume. That traceability is the
thing to walk the judges through.

WHAT CHANGED AND WHY
--------------------

1. Sorting is now deterministic on ties. `sorted(..., key=final_score)` alone
   leaves equally-scored candidates in whatever order the filesystem returned
   them, so two runs on the same folder could print different rankings. Ties
   now break on name. A demo that reorders itself between runs is a demo a
   judge stops trusting.

2. Explanations name the EVIDENCE, not just the skill. The original said
   "Matched required skills: Node.js". This version can say which line of the
   resume proved it, and distinguishes "listed React" from "has Next.js, which
   is adjacent" from "never says Docker but describes containerised services" -
   because the matcher now tracks that difference.

3. The semantic sentence is no longer a fixed 0.5/0.25 cut on a raw cosine.
   Raw cosine has no absolute meaning and its scale differs between the
   transformer and the TF-IDF fallback, so "strong alignment" meant different
   things depending on which encoder happened to load. The engine calibrates
   against the observed distribution of the current batch first.

4. Added `explain_difference()` - "why is X above Y" - because the problem
   statement lists it as a bonus and it is the question a recruiter actually
   asks.

WHAT DID NOT CHANGE
-------------------
`rank_candidates(scored)`, `explain_candidate(candidate)` and
`explain_top_n(ranked, n)` keep their names, arguments and return types.
"""

from __future__ import annotations

from typing import Dict, List

from engine_bridge import engine_compare, engine_explain


def rank_candidates(scored_candidates: List[Dict]) -> List[Dict]:
    """Sort best-to-worst and add a 1-indexed `rank`.

    If the dicts came from `matcher.score_batch` they are already ranked by the
    engine; this re-sorts harmlessly and is safe to call either way.
    """
    ranked = sorted(
        scored_candidates,
        key=lambda c: (-float(c.get("final_score", 0.0)), str(c.get("filename", ""))),
    )
    for i, candidate in enumerate(ranked, start=1):
        candidate["rank"] = i
    return ranked


def explain_candidate(candidate: Dict) -> str:
    """Natural-language explanation for one scored candidate.

    Uses the engine's generator when the full trace is present (it can quote
    evidence lines), and falls back to the original template when handed a plain
    dict - so this still works on hand-built test fixtures.
    """
    engine_candidate, jd = candidate.get("_engine"), candidate.get("_jd")
    if engine_candidate is not None and jd is not None:
        try:
            return engine_explain(engine_candidate, jd)
        except Exception:                          # noqa: BLE001
            pass
    if candidate.get("explanation"):
        return candidate["explanation"]

    # Fallback: the original template, with the evidence added where we have it.
    name = candidate.get("candidate") or candidate.get("filename", "unknown")
    matched = candidate.get("matched_required", [])
    missing = candidate.get("missing_required", [])
    sem = float(candidate.get("semantic_score", 0.0))

    lines = [f"Rank {candidate.get('rank', '?')}: {name} "
             f"(score: {candidate.get('final_score', 0.0)})"]

    lines.append(f"  Matched required skills: {', '.join(matched)}" if matched
                 else "  Matched required skills: none found")
    lines.append(f"  Missing required skills: {', '.join(missing)}" if missing
                 else "  All required skills present")

    for ev in candidate.get("semantic_evidence", [])[:1]:
        lines.append(f"  Closest match to \"{ev['jd_requirement'][:60]}\": "
                     f"\"{ev['resume_line'][:70]}\" ({ev['similarity']:.2f})")

    if sem >= 0.6:
        lines.append("  Strong overall semantic alignment with the JD's focus.")
    elif sem >= 0.3:
        lines.append("  Moderate semantic alignment - relevant background, some gaps.")
    else:
        lines.append("  Weak semantic alignment with the JD's overall focus.")

    conf = candidate.get("confidence")
    if conf:
        lines.append(f"  Evidence confidence: {conf['score']:.0f}/100 ({conf['band']}) "
                     f"- {'; '.join(conf.get('reasons', [])[:2])}")

    for flag in candidate.get("integrity_flags", [])[:2]:
        lines.append(f"  [{flag['severity'].upper()}] {flag['title']}")

    return "\n".join(lines)


def explain_top_n(ranked_candidates: List[Dict], n: int = 3) -> str:
    """Explanations for the top N, as one printable string."""
    return "\n\n".join(explain_candidate(c) for c in ranked_candidates[:n])


def explain_difference(a: Dict, b: Dict) -> str:
    """Why is A ranked above B? (bonus feature in the problem statement)"""
    ea, eb = a.get("_engine"), b.get("_engine")
    jd = a.get("_jd") or b.get("_jd")
    if ea is not None and eb is not None and jd is not None:
        try:
            return engine_compare(ea, eb, jd)
        except Exception:                          # noqa: BLE001
            pass

    if float(a.get("final_score", 0)) < float(b.get("final_score", 0)):
        a, b = b, a
    a_name = a.get("candidate") or a.get("filename")
    b_name = b.get("candidate") or b.get("filename")
    only_a = sorted(set(a.get("matched_required", [])) - set(b.get("matched_required", [])))
    only_b = sorted(set(b.get("matched_required", [])) - set(a.get("matched_required", [])))

    parts = [f"{a_name} scores {a.get('final_score', 0):.3f} against "
             f"{b_name}'s {b.get('final_score', 0):.3f}."]
    kw_delta = float(a.get("keyword_score", 0)) - float(b.get("keyword_score", 0))
    sem_delta = float(a.get("semantic_score", 0)) - float(b.get("semantic_score", 0))
    driver = "keyword matching" if abs(kw_delta) >= abs(sem_delta) else "semantic matching"
    parts.append(f"The gap is driven mainly by {driver} "
                 f"(keyword {kw_delta:+.3f}, semantic {sem_delta:+.3f}).")
    if only_a:
        parts.append(f"{a_name} covers {', '.join(only_a)} which {b_name} does not.")
    if only_b:
        parts.append(f"{b_name} brings {', '.join(only_b)}, but not enough to close the gap.")
    return " ".join(parts)


def to_json_safe(ranked: List[Dict]) -> List[Dict]:
    """Strip the `_engine` objects so the result can be json.dump'd."""
    return [{k: v for k, v in c.items() if not k.startswith("_")} for c in ranked]


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    fake_scored = [
        {"filename": "alice.pdf", "final_score": 0.81, "keyword_score": 0.9,
         "semantic_score": 0.7, "matched_required": ["Node.js", "MongoDB"],
         "missing_required": [], "matched_preferred": ["Docker"],
         "missing_preferred": ["AWS"]},
        {"filename": "bob.pdf", "final_score": 0.55, "keyword_score": 0.5,
         "semantic_score": 0.6, "matched_required": ["MongoDB"],
         "missing_required": ["Node.js"], "matched_preferred": [],
         "missing_preferred": ["Docker", "AWS"]},
        {"filename": "carol.pdf", "final_score": 0.30, "keyword_score": 0.2,
         "semantic_score": 0.4, "matched_required": [],
         "missing_required": ["Node.js", "MongoDB"], "matched_preferred": [],
         "missing_preferred": ["Docker", "AWS"]},
    ]

    ranked = rank_candidates(fake_scored)
    print(explain_top_n(ranked))
    print()
    print("--- difference ---")
    print(explain_difference(ranked[0], ranked[1]))
