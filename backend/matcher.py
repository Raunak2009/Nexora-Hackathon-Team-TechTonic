"""Matching layer - same public API as the original, backed by the engine.

No API key, no external service, nothing paid. Same as before.

WHAT CHANGED AND WHY
--------------------

1. THE MODEL NO LONGER LOADS AT IMPORT TIME.
   The original ran `SentenceTransformer("all-MiniLM-L6-v2")` at module import
   and caught only `ImportError`. If the package was installed but the model
   could not be fetched (no wifi at the venue, HuggingFace slow, disk full) the
   real exception is `OSError`/`HTTPError`, which was not caught - so importing
   matcher.py crashed the entire backend. Now the encoder is built lazily and
   any failure falls back to the local TF-IDF path with a note.

2. SEMANTIC MATCHING IS CHUNK-LEVEL, NOT WHOLE-DOCUMENT.
   The original embedded the entire JD as one vector and the entire resume as
   another. Averaging three pages into a single 384-dim vector washes out the
   two lines that decide the hire. A candidate whose resume is 95% React and
   one line of Node scores the same as one who genuinely does both.
   The engine embeds every resume bullet separately, compares each JD
   requirement against every bullet, and keeps the best matches - weighted by
   which section they came from. It is the same cosine similarity, applied
   where it actually discriminates. It also gives us the exact resume line
   behind each match, which is what the explanations quote.

3. THE TF-IDF FALLBACK NO LONGER FITS ON TWO DOCUMENTS.
   `TfidfVectorizer().fit_transform([jd_text, resume_text])` computes IDF over a
   corpus of size 2, where every term has df of 1 or 2. That IDF carries almost
   no information, so the "fallback" was close to raw term overlap. The engine
   fits TF-IDF + SVD across the whole candidate pool, so IDF means something.

4. FIXED: `kw_score = req_score or pref_score`.
   `0.0 or x` evaluates to `x` in Python. A candidate who matched NONE of the
   required skills silently got scored on their nice-to-haves instead - exactly
   backwards, and it would have quietly promoted weak candidates.

5. KEYWORD MATCHING IS FOUR-TIER, NOT BOOLEAN.
   `_fuzzy_contains` returned True/False. Reality has a middle: the JD asks for
   React and the resume says Next.js; the JD asks for Docker and the resume
   says "containerised services". Those are not the same as having the skill,
   and they are not the same as not having it. Statuses now are
   exact (1.0) / related (0.55) / semantic (<=0.35) / missing (0.0), each
   carrying the resume line it fired on.

WHAT DID NOT CHANGE
-------------------
`keyword_match`, `semantic_score` and `score_candidate` keep their names,
arguments and return shapes. `score_candidate` still returns `final_score`,
`keyword_score`, `semantic_score`, `matched_required`, `missing_required`,
`matched_preferred`, `missing_preferred` - plus richer fields alongside.
"""

from __future__ import annotations

import difflib
import re
from typing import Dict, List, Optional, Tuple

from engine_bridge import (
    SIMPLE_WEIGHTS,
    SemanticMatcher,
    ShortlistEngine,
    SimpleWeights,
    get_ontology,
)

# Set by _semantic_backend() on first use. Exposed for the /health endpoint and
# so the CLI can tell you which path is live before you demo.
_USE_TRANSFORMER: Optional[bool] = None
_BACKEND_NOTE = "not initialised yet"


# ---------------------------------------------------------------------------
# 1. Keyword matching
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9+.# ]", "", text.lower()).strip()


def _fuzzy_contains(skill: str, resume_text: str, threshold: float = 0.85) -> bool:
    """True if `skill` appears in `resume_text`, directly or as a near match.

    Kept from the original (it is a reasonable standalone check and other code
    may call it), with one fix: the sliding window now also tries windows one
    word longer and one shorter, so "Node JS" matches "Node.js" and
    "React Native" does not falsely match "React".
    """
    norm_skill = _normalize(skill)
    norm_text = _normalize(resume_text)
    if not norm_skill:
        return False
    if norm_skill in norm_text:
        return True

    words = norm_text.split()
    skill_len = max(1, len(norm_skill.split()))
    for span in {max(1, skill_len - 1), skill_len, skill_len + 1}:
        for i in range(len(words) - span + 1):
            window = " ".join(words[i:i + span])
            if difflib.SequenceMatcher(None, norm_skill, window).ratio() >= threshold:
                return True
    return False


def keyword_match(required_skills: List[str],
                  resume_text: str) -> Tuple[float, List[str], List[str]]:
    """(score 0-1, matched, missing) for a list of skills against resume text.

    Now resolved through the skill ontology rather than raw string comparison,
    so "reactjs", "React.js", "React Hooks" and the typo "Reactjs " all count as
    React, and "Mongo DB" counts as MongoDB.

    Behaviour change worth flagging: an EMPTY skill list returns 0.0, not 1.0.
    The original returned a perfect score when the JD parser found no skills,
    which meant a JD that failed to parse handed every candidate full marks.
    A score of "we found nothing to check" should not look like "passed
    everything".
    """
    if not required_skills:
        return 0.0, [], []

    ontology = get_ontology()
    found = {h.key for h in ontology.extract(resume_text, section="skills")}

    matched, missing = [], []
    for skill in required_skills:
        key = ontology.resolve(skill)
        if (key and key in found) or _fuzzy_contains(skill, resume_text):
            matched.append(skill)
        else:
            missing.append(skill)

    return len(matched) / len(required_skills), matched, missing


# ---------------------------------------------------------------------------
# 2. Semantic matching
# ---------------------------------------------------------------------------
def _semantic_backend() -> Tuple[bool, str]:
    """Which encoder is available? Resolved once, lazily, never at import."""
    global _USE_TRANSFORMER, _BACKEND_NOTE
    if _USE_TRANSFORMER is not None:
        return _USE_TRANSFORMER, _BACKEND_NOTE

    try:
        from app.matching.semantic import MiniLMEncoder

        MiniLMEncoder()
        _USE_TRANSFORMER, _BACKEND_NOTE = True, "sentence-transformers/all-MiniLM-L6-v2"
    except ImportError:
        _USE_TRANSFORMER = False
        _BACKEND_NOTE = "sentence-transformers not installed - using TF-IDF+SVD"
    except Exception as exc:                       # noqa: BLE001
        _USE_TRANSFORMER = False
        _BACKEND_NOTE = f"embedding model unavailable ({type(exc).__name__}) - using TF-IDF+SVD"
    return _USE_TRANSFORMER, _BACKEND_NOTE


def semantic_backend_info() -> Dict[str, object]:
    """For /health and the CLI banner - know before you demo."""
    ok, note = _semantic_backend()
    return {"using_transformer": ok, "detail": note}


def semantic_score(jd_text: str, resume_text: str) -> float:
    """0-1 similarity between a JD and one resume.

    Standalone helper, kept for compatibility. It embeds the two documents
    whole, which is the weaker approach described at the top of this file - so
    prefer `score_candidate` or `score_batch`, which do it at bullet level
    against the real candidate pool. Left here because a quick two-document
    similarity is genuinely useful when debugging.
    """
    import numpy as np

    from app.matching.semantic import build_encoder

    encoder, _ = build_encoder([jd_text, resume_text])
    vecs = encoder.encode([jd_text, resume_text])
    if vecs.shape[0] < 2:
        return 0.0
    return float(np.clip(vecs[0] @ vecs[1], 0.0, 1.0))


# ---------------------------------------------------------------------------
# 3. Scoring
# ---------------------------------------------------------------------------
def _to_legacy_dict(candidate, keyword_weight: float, semantic_weight: float,
                    jd=None) -> Dict:
    """Engine RankedCandidate -> the dict shape this module has always returned."""
    r = candidate.resume
    return {
        # original keys
        "filename": r.path.name,
        "final_score": round(candidate.score / 100.0, 4),      # 0-1, as before
        "keyword_score": round(candidate.keyword_score, 4),
        "semantic_score": round(candidate.semantic_score, 4),
        "matched_required": [m.canonical for m in candidate.required_matches
                             if m.status != "missing"],
        "missing_required": [m.canonical for m in candidate.missing_required],
        "matched_preferred": [m.canonical for m in candidate.preferred_matches
                              if m.status != "missing"],
        "missing_preferred": [m.canonical for m in candidate.preferred_matches
                              if m.status == "missing"],

        # added - all of it comes free from the engine
        "score_100": candidate.score,
        "candidate": r.name,
        "doc_id": r.doc_id,
        "email": r.email,
        "years_experience": r.years_experience,
        "education": r.education_label,
        "skill_score": round(candidate.subscores.required_skills, 4),
        "subscores": candidate.subscores.to_dict(candidate.weights_used or None),
        "skill_detail": [m.to_dict() for m in candidate.required_matches],
        "preferred_detail": [m.to_dict() for m in candidate.preferred_matches],
        "semantic_evidence": [
            {"jd_requirement": m.requirement, "resume_line": m.evidence,
             "similarity": round(m.similarity, 3), "section": m.evidence_section}
            for m in candidate.semantic_result.best_matches
        ],
        "confidence": candidate.confidence.to_dict() if candidate.confidence else None,
        "integrity_flags": [f.to_dict() for f in candidate.integrity_flags],
        "flag_level": candidate.worst_flag,
        "explanation": candidate.explanation,
        "weights": {"keyword": keyword_weight, "semantic": semantic_weight},
        "_engine": candidate,
        "_jd": jd,
    }


def _weights(keyword_weight: float, semantic_weight: float) -> SimpleWeights:
    """Map the caller's two knobs onto the engine's weighting.

    Experience keeps its default share so that passing 0.5/0.5 behaves the way
    the original did - keyword and semantic equally balanced - without silently
    throwing away the experience signal.
    """
    total = (keyword_weight + semantic_weight) or 1.0
    room = 1.0 - SIMPLE_WEIGHTS.experience
    return SimpleWeights(
        keyword=room * keyword_weight / total,
        semantic=room * semantic_weight / total,
        experience=SIMPLE_WEIGHTS.experience,
    )


def score_batch(jd_parsed: Dict, resumes_parsed: List[Dict],
                keyword_weight: float = 0.5,
                semantic_weight: float = 0.5) -> List[Dict]:
    """Score a whole pool at once. THIS is the function to call.

    Scoring one resume at a time is not just slower - it is less correct. BM25's
    IDF and the semantic calibration are both computed from the candidate pool:
    "JavaScript" is a weak signal when every applicant has it and a strong one
    when three do, and the engine can only know which by seeing them together.

    `score_candidate` below scores one resume against a pool of one, which
    throws that away. It is kept for compatibility; use this instead.
    """
    jd = jd_parsed.get("_engine")
    if jd is None:
        from parser import parse_jd as _pj
        jd = _pj(jd_parsed.get("_raw", ""))["_engine"]

    resumes = []
    for r in resumes_parsed:
        engine_resume = r.get("_engine")
        if engine_resume is None:
            from parser import parse_resume_text
            engine_resume = parse_resume_text(
                r.get("_raw", ""), r.get("_filename", "unknown"))["_engine"]
        resumes.append(engine_resume)

    engine = ShortlistEngine(jd, resumes)
    engine.run(weights=_weights(keyword_weight, semantic_weight).to_weights(),
               explain_top=len(resumes))
    return [_to_legacy_dict(c, keyword_weight, semantic_weight, engine.jd)
            for c in engine.candidates]


def score_candidate(jd_parsed: Dict, resume_parsed: Dict,
                    keyword_weight: float = 0.5,
                    semantic_weight: float = 0.5) -> Dict:
    """Score ONE candidate. Same signature and return shape as the original.

    Note: BM25 and the semantic calibration are pool-relative, so a single
    resume scored alone gets a lexical score of 1.0 by definition (it is the
    best of one). Prefer `score_batch` for anything you will actually rank.
    """
    return score_batch(jd_parsed, [resume_parsed], keyword_weight, semantic_weight)[0]


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from parser import parse_jd, parse_resume_text

    jd = parse_jd(
        "Backend Developer role.\n\n"
        "Requirements:\n- Node.js\n- MongoDB\n- 2+ years experience\n\n"
        "Preferred:\n- Docker\n- AWS\n"
    )

    good = parse_resume_text(
        "Backend intern.\n\nExperience\n"
        "Built REST APIs with Express and MongoDB. Deployed services using Docker.\n",
        "good_candidate.txt")
    weak = parse_resume_text(
        "Frontend developer skilled in React, CSS, and Figma design handoff.\n",
        "weak_candidate.txt")

    info = semantic_backend_info()
    print("Semantic backend:", info["detail"])
    print("JD required:", jd["required_skills"], "| preferred:", jd["nice_to_have_skills"])
    print()

    for row in score_batch(jd, [good, weak]):
        print(f"{row['filename']:<22} final={row['final_score']:.3f}  "
              f"keyword={row['keyword_score']:.3f}  semantic={row['semantic_score']:.3f}")
        print(f"  matched : {row['matched_required']}")
        print(f"  missing : {row['missing_required']}")
        # The interesting one: 'good' never writes "Node.js", only "Express".
        for ev in row["semantic_evidence"][:1]:
            print(f"  evidence: \"{ev['resume_line'][:70]}\" ({ev['similarity']:.2f})")
        print()
