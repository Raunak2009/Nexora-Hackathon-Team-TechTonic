"""
Ranking layer for the Smart Shortlisting Engine.

Takes scored candidates (from matcher.score_candidate) and:
1. Sorts them best-to-worst.
2. Generates a human-readable explanation for the top 3 — which
   required skills matched, which are missing, and a one-line note
   on the semantic fit.

No LLM/API call here — explanations are built directly from the
matched/missing skill lists the matcher already computed, so they're
fully traceable back to the actual matching logic (this is what you'll
walk the judges through).
"""

from typing import Dict, List


def rank_candidates(scored_candidates: List[Dict]) -> List[Dict]:
    """Sort candidates by final_score, descending. Adds a 1-indexed rank."""
    ranked = sorted(scored_candidates, key=lambda c: c["final_score"], reverse=True)
    for i, candidate in enumerate(ranked, start=1):
        candidate["rank"] = i
    return ranked


def explain_candidate(candidate: Dict) -> str:
    """
    Builds a short natural-language explanation from a single scored
    candidate dict (as returned by matcher.score_candidate).
    """
    name = candidate["filename"]
    matched = candidate["matched_required"]
    missing = candidate["missing_required"]
    sem = candidate["semantic_score"]

    lines = [f"Rank {candidate['rank']}: {name} (score: {candidate['final_score']})"]

    if matched:
        lines.append(f"  Matched required skills: {', '.join(matched)}")
    else:
        lines.append("  Matched required skills: none found")

    if missing:
        lines.append(f"  Missing required skills: {', '.join(missing)}")
    else:
        lines.append("  All required skills present")

    if sem >= 0.5:
        lines.append("  Strong overall semantic alignment with the JD's focus.")
    elif sem >= 0.25:
        lines.append("  Moderate semantic alignment — relevant background, some gaps.")
    else:
        lines.append("  Weak semantic alignment with the JD's overall focus.")

    return "\n".join(lines)


def explain_top_n(ranked_candidates: List[Dict], n: int = 3) -> str:
    return "\n\n".join(explain_candidate(c) for c in ranked_candidates[:n])


if _name_ == "_main_":
    fake_scored = [
        {"filename": "alice.pdf", "final_score": 0.81, "keyword_score": 0.9,
         "semantic_score": 0.7, "matched_required": ["Node.js", "MongoDB"],
         "missing_required": [], "matched_preferred": ["Docker"], "missing_preferred": ["AWS"]},
        {"filename": "bob.pdf", "final_score": 0.55, "keyword_score": 0.5,
         "semantic_score": 0.6, "matched_required": ["MongoDB"],
         "missing_required": ["Node.js"], "matched_preferred": [], "missing_preferred": ["Docker", "AWS"]},
        {"filename": "carol.pdf", "final_score": 0.30, "keyword_score": 0.2,
         "semantic_score": 0.4, "matched_required": [],
         "missing_required": ["Node.js", "MongoDB"], "matched_preferred": [], "missing_preferred": ["Docker", "AWS"]},
    ]

    ranked = rank_candidates(fake_scored)
    print(explain_top_n(ranked))