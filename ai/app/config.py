"""Central configuration for the Smart Shortlisting Engine.

Everything tunable lives here so that during judging you can point at ONE file
and say "these are our knobs, here is why each is set this way".
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
AI_DIR = APP_DIR.parent
DATA_DIR = AI_DIR / "data"
RESOURCES_DIR = APP_DIR / "resources"

# ---------------------------------------------------------------------------
# Semantic model
# ---------------------------------------------------------------------------
# all-MiniLM-L6-v2: 384-dim sentence embeddings, ~90MB, downloaded ONCE from
# HuggingFace and cached in ~/.cache/huggingface. After the first run it is
# fully offline. No API key, no paid service, no LLM scoring.
EMBEDDING_MODEL = os.getenv("NEXORA_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# If the model cannot be loaded (no network at the venue, torch missing, ...)
# we transparently fall back to TF-IDF + Truncated SVD (Latent Semantic
# Analysis), which is pure scikit-learn and always available.
ALLOW_LSA_FALLBACK = True

# Force the fallback for testing / low-resource machines.
FORCE_LSA = os.getenv("NEXORA_FORCE_LSA", "0") == "1"


# ---------------------------------------------------------------------------
# Score fusion weights
# ---------------------------------------------------------------------------
@dataclass
class Weights:
    """How the five sub-scores combine into the final 0-100 score.

    Rationale (this is the answer to "why these numbers?"):
      * required_skills is the single biggest lever because the problem
        statement is explicit that "specific tools and technologies named in a
        JD still matter - a role that explicitly asks for certain skills
        shouldn't be satisfied by only loosely related experience".
      * semantic is the second biggest because it is what catches
        "built REST APIs with Express and MongoDB" for a Node.js role.
      * lexical (BM25) is a real but smaller signal: it rewards resumes that
        use the JD's own vocabulary, and it is rank-stable and cheap.
      * preferred_skills and experience are tie-breakers, not drivers.
    """

    required_skills: float = 0.34
    semantic: float = 0.26
    lexical: float = 0.16
    preferred_skills: float = 0.12
    experience: float = 0.12

    def as_dict(self) -> dict[str, float]:
        return {
            "required_skills": self.required_skills,
            "semantic": self.semantic,
            "lexical": self.lexical,
            "preferred_skills": self.preferred_skills,
            "experience": self.experience,
        }

    def normalized(self) -> dict[str, float]:
        d = self.as_dict()
        total = sum(d.values()) or 1.0
        return {k: v / total for k, v in d.items()}


WEIGHTS = Weights()


@dataclass
class SimpleWeights:
    """The three-knob view the recruiter UI exposes.

    The engine really has five sub-scores, but a recruiter does not want five
    sliders - they want "how much do I care about the exact tools named" versus
    "how much do I care about what the work actually means". So the UI drives
    three knobs and we expand them back into the five internal weights.

    The defaults below expand to EXACTLY the default `Weights` above, so moving
    the sliders to their default position reproduces the engine's own ranking.

      keyword    = required_skills + preferred_skills + lexical   (0.34+0.12+0.16)
      semantic   = semantic                                        (0.26)
      experience = experience                                      (0.12)
    """

    keyword: float = 0.62
    semantic: float = 0.26
    experience: float = 0.12

    # How the keyword budget is split internally. Exposed so an advanced user
    # can retune, but the UI does not need to show it.
    required_share: float = 0.34 / 0.62
    preferred_share: float = 0.12 / 0.62
    lexical_share: float = 0.16 / 0.62

    def to_weights(self) -> Weights:
        total = (self.keyword + self.semantic + self.experience) or 1.0
        kw = self.keyword / total
        share_total = (self.required_share + self.preferred_share + self.lexical_share) or 1.0
        return Weights(
            required_skills=kw * self.required_share / share_total,
            preferred_skills=kw * self.preferred_share / share_total,
            lexical=kw * self.lexical_share / share_total,
            semantic=self.semantic / total,
            experience=self.experience / total,
        )

    @classmethod
    def from_weights(cls, w: Weights) -> "SimpleWeights":
        d = w.normalized()
        kw = d["required_skills"] + d["preferred_skills"] + d["lexical"]
        return cls(
            keyword=kw,
            semantic=d["semantic"],
            experience=d["experience"],
            required_share=(d["required_skills"] / kw) if kw else 0.55,
            preferred_share=(d["preferred_skills"] / kw) if kw else 0.19,
            lexical_share=(d["lexical"] / kw) if kw else 0.26,
        )

    def as_dict(self) -> dict[str, float]:
        total = (self.keyword + self.semantic + self.experience) or 1.0
        return {
            "keyword": round(self.keyword / total, 4),
            "semantic": round(self.semantic / total, 4),
            "experience": round(self.experience / total, 4),
        }


SIMPLE_WEIGHTS = SimpleWeights()

# ---------------------------------------------------------------------------
# Integrity / confidence
# ---------------------------------------------------------------------------
# A resume claiming this many more years than the role's ceiling gets flagged as
# a seniority mismatch (an "intern" with 5 years of industry experience).
SENIORITY_CEILING = {"intern": 2.0, "junior": 3.5, "mid": 8.0, "senior": 40.0}

# More distinct skills than this, with fewer than N words of surrounding prose
# per skill, reads as a keyword dump rather than a description of real work.
KEYWORD_STUFF_MIN_SKILLS = 22
KEYWORD_STUFF_WORDS_PER_SKILL = 28

# ---------------------------------------------------------------------------
# Skill matching
# ---------------------------------------------------------------------------
# Credit given when the resume does not have skill X itself but has a skill the
# ontology marks as closely related (e.g. JD wants "React", resume has
# "Next.js"). Partial, never full - a related skill is not the same skill.
RELATED_SKILL_CREDIT = 0.55

# Credit given when the resume never names the skill but a sentence in it is
# semantically very close to the requirement text. Lower still, because this is
# the weakest kind of evidence and must not outrank an explicit mention.
SEMANTIC_SKILL_CREDIT = 0.35

# Cosine similarity a resume sentence must reach before it counts as semantic
# evidence for a specific required skill.
SEMANTIC_SKILL_THRESHOLD = 0.45

# Fuzzy string matching threshold (0-100) for catching typos like "Javascrpit".
FUZZY_THRESHOLD = 88

# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------
BM25_K1 = 1.5
BM25_B = 0.75

# ---------------------------------------------------------------------------
# Semantic chunking
# ---------------------------------------------------------------------------
# Resumes are embedded as chunks (roughly bullet/sentence level) rather than one
# giant vector: a 3-page resume averaged into one vector washes out the two
# lines that actually matter. We score JD requirements against the BEST matching
# chunks and average the top-k.
SEMANTIC_TOP_K_CHUNKS = 3
MIN_CHUNK_WORDS = 4
MAX_CHUNK_WORDS = 80

# ---------------------------------------------------------------------------
# Experience fit
# ---------------------------------------------------------------------------
# For an internship / junior role, MORE experience is not linearly better.
# We reward meeting the bar and stop rewarding far beyond it.
EXPERIENCE_OVERSHOOT_TOLERANCE = 2.0  # years beyond the ask before we stop caring

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".rtf", ".xml"}
