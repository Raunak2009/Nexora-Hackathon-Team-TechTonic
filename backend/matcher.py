"""
Matching layer for the Smart Shortlisting Engine.

Two independent scoring mechanisms, combined at the end:

1. Keyword matching  -> did the resume explicitly mention the skills the
   JD asks for (allowing for minor spelling/formatting variation)?
2. Semantic matching  -> how close in meaning is the resume to the JD,
   even if it never uses the exact same words?

No API key / external service required anywhere in this file.

Semantic matching prefers sentence-transformers (better quality embeddings)
but falls back automatically to a TF-IDF + cosine-similarity approach
(scikit-learn, pure local, no model download) if sentence-transformers
isn't installed. This means the code still runs even before you've set
up the heavier dependency.
"""

import difflib
import re
from typing import Dict, List, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Try to load the higher-quality embedding model. If it's not installed,
# we fall back to TF-IDF further down — semantic_score() hides this
# switch from the caller.
try:
    from sentence_transformers import SentenceTransformer
    _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    _USE_TRANSFORMER = True
except ImportError:
    _EMBED_MODEL = None
    _USE_TRANSFORMER = False


# ---------------------------------------------------------------------------
# 1. Keyword matching
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9+.# ]", "", text.lower()).strip()


def _fuzzy_contains(skill: str, resume_text: str, threshold: float = 0.85) -> bool:
    """
    True if skill appears in resume_text, either as a direct substring
    or as a close fuzzy match against some word/phrase window in the text.
    Handles things like 'Node.js' vs 'NodeJS' vs 'Node JS'.
    """
    norm_skill = _normalize(skill)
    norm_text = _normalize(resume_text)

    if norm_skill in norm_text:
        return True

    # Slide a window of similar length across the resume's word list and
    # fuzzy-compare, catching near-spellings without needing a whole
    # extra dependency (difflib is stdlib).
    words = norm_text.split()
    skill_len = max(1, len(norm_skill.split()))
    for i in range(len(words) - skill_len + 1):
        window = " ".join(words[i:i + skill_len])
        ratio = difflib.SequenceMatcher(None, norm_skill, window).ratio()
        if ratio >= threshold:
            return True
    return False


def keyword_match(required_skills: List[str], resume_text: str) -> Tuple[float, List[str], List[str]]:
    """
    Returns (score 0-1, matched_skills, missing_skills) for a list of
    required/preferred skills against one resume's full text.
    """
    if not required_skills:
        return 1.0, [], []

    matched, missing = [], []
    for skill in required_skills:
        if _fuzzy_contains(skill, resume_text):
            matched.append(skill)
        else:
            missing.append(skill)

    score = len(matched) / len(required_skills)
    return score, matched, missing


# ---------------------------------------------------------------------------
# 2. Semantic matching
# ---------------------------------------------------------------------------

def _semantic_score_transformer(jd_text: str, resume_text: str) -> float:
    embeddings = _EMBED_MODEL.encode([jd_text, resume_text])
    sim = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
    return float(sim)


def _semantic_score_tfidf(jd_text: str, resume_text: str) -> float:
    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf = vectorizer.fit_transform([jd_text, resume_text])
    sim = cosine_similarity(tfidf[0], tfidf[1])[0][0]
    return float(sim)


def semantic_score(jd_text: str, resume_text: str) -> float:
    """Returns a 0-1 similarity score between JD text and resume text."""
    if _USE_TRANSFORMER:
        return _semantic_score_transformer(jd_text, resume_text)
    return _semantic_score_tfidf(jd_text, resume_text)


# ---------------------------------------------------------------------------
# 3. Combined score for one candidate
# ---------------------------------------------------------------------------

def score_candidate(
    jd_parsed: Dict,
    resume_parsed: Dict,
    keyword_weight: float = 0.5,
    semantic_weight: float = 0.5,
) -> Dict:
    """
    jd_parsed: output of parser.parse_jd()
    resume_parsed: output of parser.parse_resume()
    """
    resume_text = resume_parsed.get("_raw", "")
    jd_text = jd_parsed.get("_raw", "")

    required = jd_parsed.get("required_skills", [])
    preferred = jd_parsed.get("nice_to_have_skills", [])

    req_score, req_matched, req_missing = keyword_match(required, resume_text)
    pref_score, pref_matched, pref_missing = keyword_match(preferred, resume_text)

    # Required skills matter more than nice-to-haves in the keyword half.
    if required and preferred:
        kw_score = 0.75 * req_score + 0.25 * pref_score
    else:
        kw_score = req_score or pref_score

    sem_score = semantic_score(jd_text, resume_text)

    final = keyword_weight * kw_score + semantic_weight * sem_score

    return {
        "filename": resume_parsed.get("_filename", "unknown"),
        "final_score": round(final, 4),
        "keyword_score": round(kw_score, 4),
        "semantic_score": round(sem_score, 4),
        "matched_required": req_matched,
        "missing_required": req_missing,
        "matched_preferred": pref_matched,
        "missing_preferred": pref_missing,
    }


if _name_ == "_main_":
    # Quick smoke test with two contrasting candidates.
    jd_parsed = {
        "_raw": "Backend Developer role. Required: Node.js, MongoDB, 2+ years experience. Preferred: Docker, AWS.",
        "required_skills": ["Node.js", "MongoDB"],
        "nice_to_have_skills": ["Docker", "AWS"],
    }

    good_resume = {
        "_filename": "good_candidate.txt",
        "_raw": "Backend intern. Built REST APIs with Express and MongoDB. Deployed services using Docker.",
    }

    weak_resume = {
        "_filename": "weak_candidate.txt",
        "_raw": "Frontend developer skilled in React, CSS, and Figma design handoff.",
    }

    print("Using transformer embeddings:" , _USE_TRANSFORMER)
    print(score_candidate(jd_parsed, good_resume))
    print(score_candidate(jd_parsed, weak_resume))