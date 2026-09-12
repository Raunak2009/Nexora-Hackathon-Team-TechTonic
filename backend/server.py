"""HTTP server entry point. THIS is what the frontend talks to.

    cd backend
    uvicorn server:app --reload --port 8000

    docs:  http://localhost:8000/docs
    index: http://localhost:8000/

Every endpoint the frontend needs is defined in ../ai/api.py. This module mounts
that app and adds a couple of backend-level conveniences on top, rather than
redefining routes - one router, one source of truth, no chance of the CLI and
the API disagreeing about a score.

The full request/response contract is in ../ai/API.md. Hand that to whoever is
writing the frontend.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

import engine_bridge  # noqa: E402,F401  (puts ../ai on sys.path)

from api import app  # noqa: E402  - the FastAPI app defined in ai/api.py

from fastapi.middleware.cors import CORSMiddleware  # noqa: E402


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# ai/api.py already allows all origins for dev. Set NEXORA_ALLOWED_ORIGINS to a
# comma-separated list to lock it down before this is exposed anywhere real.
def _tighten_cors() -> None:
    import os

    origins = os.getenv("NEXORA_ALLOWED_ORIGINS")
    if not origins:
        return
    allowed = [o.strip() for o in origins.split(",") if o.strip()]
    app.user_middleware = [m for m in app.user_middleware
                           if m.cls is not CORSMiddleware]
    app.add_middleware(CORSMiddleware, allow_origins=allowed,
                       allow_methods=["*"], allow_headers=["*"])
    app.middleware_stack = app.build_middleware_stack()


_tighten_cors()


# ---------------------------------------------------------------------------
# Index - so hitting the root in a browser tells you what exists
# ---------------------------------------------------------------------------
@app.get("/", tags=["meta"])
def index() -> dict:
    from matcher import semantic_backend_info

    return {
        "service": "Smart Shortlisting Engine",
        "version": app.version,
        "docs": "/docs",
        "contract": "see ai/API.md",
        "semantic_backend": semantic_backend_info(),
        "flow": [
            "POST /jobs                             -> job_id",
            "POST /jobs/{job_id}/rank/upload        -> run_id + ranking",
            "GET  /runs/{run_id}/matrix             -> skill table",
            "GET  /runs/{run_id}/candidates/{who}   -> candidate page",
            "GET  /runs/{run_id}/top?n=3            -> top-3 comparison",
            "POST /runs/{run_id}/weights            -> move sliders, re-rank",
            "POST /runs/{run_id}/filter             -> filtered view",
            "POST /runs/{run_id}/chat               -> recruiter chat",
            "GET  /runs/{run_id}/charts             -> plot-ready data",
            "GET  /runs/{run_id}/report/{kind}.pdf  -> download",
        ],
        "endpoints": sorted(
            {r.path for r in app.routes if getattr(r, "include_in_schema", True)}
        ),
    }


@app.get("/ready", tags=["meta"])
def ready() -> dict:
    """Deeper than /health: actually exercises the pipeline once.

    Point your deploy check at this rather than /health - /health only says the
    process is up, this says the engine can genuinely parse and score.
    """
    from engine_bridge import ENGINE_DIR, ShortlistEngine

    jd = ENGINE_DIR / "data" / "jd" / "Sample_JD.txt"
    pool = ENGINE_DIR / "data" / "validation"
    if not jd.exists() or not pool.exists():
        return {"ready": False, "reason": "sample data missing from ai/data"}

    try:
        engine = ShortlistEngine.from_folder(jd, pool)
        engine.run()
        top = engine.candidates[0]
        return {
            "ready": True,
            "encoder": engine.encoder_name,
            "notes": engine.encoder_notes,
            "self_test": {
                "pool": len(engine.candidates),
                "top": top.resume.name,
                "top_score": top.score,
                "spread": round(top.score - engine.candidates[-1].score, 1),
            },
        }
    except Exception as exc:                        # noqa: BLE001
        return {"ready": False, "reason": f"{type(exc).__name__}: {exc}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
