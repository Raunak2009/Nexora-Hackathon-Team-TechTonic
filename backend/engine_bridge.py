"""The one place in `backend/` that knows where the scoring engine lives.

Design decision worth stating plainly, because it is the reason this folder
looks the way it does:

    backend/ does NOT reimplement scoring. It wraps ../ai.

The alternative - keeping a second, simpler scorer here - means two pieces of
code that both claim to rank candidates. They drift within hours, and at some
point the API returns one number while the CLI prints another. On a hackathon
clock that is the failure that actually kills a demo.

So every module in this folder keeps the function names and signatures the team
already wrote against (`parse_resume`, `parse_jd`, `score_candidate`,
`rank_candidates`, `explain_top_n`), and each one delegates to the engine.
Existing calling code keeps working; the numbers behind it get much better.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
AI_DIR = REPO_ROOT / "ai"

_HELP = f"""
Could not find the scoring engine.

Expected it at: {AI_DIR}

The repo layout should be:

    Nexora-Hackathon-Team-TechTonic/
      ai/          <- the scoring engine (app/, cli.py, api.py, data/)
      backend/     <- this folder
      frontend/

If you moved things around, set the NEXORA_AI_DIR environment variable to the
folder that contains `app/`:

    export NEXORA_AI_DIR=/path/to/ai
"""


def _resolve_ai_dir() -> Path:
    import os

    override = os.getenv("NEXORA_AI_DIR")
    candidates = [Path(override)] if override else []
    candidates += [
        AI_DIR,
        REPO_ROOT / "ai",
        BACKEND_DIR / "ai",
        REPO_ROOT.parent / "ai",
    ]
    for path in candidates:
        if (path / "app" / "pipeline.py").exists():
            return path.resolve()
    raise ImportError(_HELP)


ENGINE_DIR = _resolve_ai_dir()
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

# Re-exported so the rest of backend/ imports from one place.
from app.config import SIMPLE_WEIGHTS, WEIGHTS, SimpleWeights, Weights  # noqa: E402
from app.matching.bias import audit_jd as engine_audit_jd  # noqa: E402
from app.matching.explain import (  # noqa: E402
    compare_candidates as engine_compare,
    explain_candidate as engine_explain,
)
from app.matching.score import rank_candidates as engine_rank  # noqa: E402
from app.matching.semantic import SemanticMatcher  # noqa: E402
from app.matching.skills import get_ontology  # noqa: E402
from app.parsing.extract import (  # noqa: E402
    ExtractedDocument,
    extract_document,
    extract_folder,
    normalize_text,
)
from app.parsing.jd import parse_jd as engine_parse_jd  # noqa: E402
from app.parsing.resume import parse_resume as engine_parse_resume  # noqa: E402
from app.pipeline import ShortlistEngine  # noqa: E402

__all__ = [
    "AI_DIR", "BACKEND_DIR", "ENGINE_DIR", "REPO_ROOT",
    "ExtractedDocument", "SemanticMatcher", "ShortlistEngine",
    "SIMPLE_WEIGHTS", "WEIGHTS", "SimpleWeights", "Weights",
    "engine_audit_jd", "engine_compare", "engine_explain", "engine_parse_jd",
    "engine_parse_resume", "engine_rank",
    "extract_document", "extract_folder", "get_ontology", "normalize_text",
]
