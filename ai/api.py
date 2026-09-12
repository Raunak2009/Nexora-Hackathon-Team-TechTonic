"""FastAPI backend for the Smart Shortlisting Engine.

    uvicorn api:app --reload --port 8000
    docs: http://localhost:8000/docs

No API keys anywhere. Every endpoint reads the ranking the engine computed
locally; nothing calls out to a paid service.

Shape of the world
    A JOB is one job description. You can have several open at once.
    A RUN is one job scored against one batch of resumes. Runs are cached in
    memory by run_id, so the UI can page, filter, chart, chat and download PDFs
    without re-parsing or re-embedding anything.

Typical frontend flow
    POST /jobs                      create a job from JD text
    POST /jobs/{job_id}/rank/upload upload the resume files -> run_id + ranking
    GET  /runs/{run_id}/matrix      the candidate x skill table
    GET  /runs/{run_id}/candidates/{who}  the per-candidate skills page
    GET  /runs/{run_id}/top?n=3     top-N comparison page
    POST /runs/{run_id}/weights     move the sliders, get a new ranking
    POST /runs/{run_id}/filter      filtered view (ranks stay pool-wide)
    POST /runs/{run_id}/chat        recruiter chat
    GET  /runs/{run_id}/charts      ready-to-plot payloads
    GET  /runs/{run_id}/report/{kind}.pdf   download
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app.config import SIMPLE_WEIGHTS, WEIGHTS, SimpleWeights  # noqa: E402
from app.matching.bias import audit_jd  # noqa: E402
from app.matching.skills import get_ontology  # noqa: E402
from app.parsing.jd import parse_jd  # noqa: E402
from app.parsing.resume import parse_resume  # noqa: E402
from app.pipeline import ShortlistEngine  # noqa: E402
from app.reporting.matrix import Filters  # noqa: E402
from app.reporting.pdf import ranked_list_pdf, skill_gap_pdf, top_explanations_pdf  # noqa: E402

app = FastAPI(title="Smart Shortlisting Engine", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten before anything real ships
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_RUNS = 25
MAX_JOBS = 50

JOBS: dict[str, dict] = {}
RUNS: dict[str, ShortlistEngine] = {}
RUN_META: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Store helpers
# ---------------------------------------------------------------------------
def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _store_job(title: str, text: str) -> dict:
    if len(JOBS) >= MAX_JOBS:
        JOBS.pop(next(iter(JOBS)))
    jd = parse_jd(text)
    job = {
        "job_id": _new_id("job"),
        "title": title or jd.title,
        "jd_text": text,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "parsed": jd.to_dict(),
        "bias_audit": audit_jd(jd),
    }
    JOBS[job["job_id"]] = job
    return job


def _get_job(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, f"Unknown job_id '{job_id}'.")
    return job


def _store_run(engine: ShortlistEngine, job_id: str | None) -> str:
    if len(RUNS) >= MAX_RUNS:
        oldest = next(iter(RUNS))
        RUNS.pop(oldest)
        RUN_META.pop(oldest, None)
    run_id = _new_id("run")
    RUNS[run_id] = engine
    RUN_META[run_id] = {
        "run_id": run_id,
        "job_id": job_id,
        "job_title": engine.jd.title,
        "pool_size": len(engine.resumes),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "encoder": engine.encoder_name,
    }
    return run_id


def _get_run(run_id: str) -> ShortlistEngine:
    engine = RUNS.get(run_id)
    if engine is None:
        raise HTTPException(404, f"Unknown or expired run_id '{run_id}'. Re-run the ranking.")
    if not engine.candidates:
        engine.run()
    return engine


async def _parse_uploads(files: list[UploadFile]):
    """Write uploads to a temp dir and parse them. Bad files are reported, not fatal."""
    import tempfile

    parsed, failures = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for up in files:
            name = up.filename or f"resume_{uuid.uuid4().hex[:6]}.txt"
            path = Path(tmp) / Path(name).name
            try:
                path.write_bytes(await up.read())
                r = parse_resume(path)
                if not r.raw_text.strip():
                    failures.append({"file": name, "reason": "no text could be extracted",
                                     "warnings": r.warnings})
                parsed.append(r)
            except Exception as exc:                       # noqa: BLE001
                failures.append({"file": name, "reason": f"{type(exc).__name__}: {exc}"})
    return parsed, failures


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class JobIn(BaseModel):
    title: str = ""
    jd_text: str = Field(..., min_length=20)


class ResumeIn(BaseModel):
    name: str
    text: str


class RankRequest(BaseModel):
    jd_text: str | None = None
    job_id: str | None = None
    resumes: list[ResumeIn]
    explain_top: int = 3
    verbose: bool = False
    weights: dict[str, float] | None = None   # keyword / semantic / experience


class WeightsIn(BaseModel):
    keyword: float | None = Field(None, ge=0, le=1)
    semantic: float | None = Field(None, ge=0, le=1)
    experience: float | None = Field(None, ge=0, le=1)
    explain_top: int = 3


class FilterIn(BaseModel):
    min_score: float | None = None
    min_years: float | None = None
    max_years: float | None = None
    must_have_skills: list[str] | None = None
    any_of_skills: list[str] | None = None
    min_education: int | None = Field(None, ge=0, le=4)
    min_confidence: float | None = Field(None, ge=0, le=100)
    hide_flagged: bool = False
    max_flag_severity: str | None = None
    freshers_only: bool = False
    search: str | None = None


class CompareIn(BaseModel):
    a: str
    b: str


class ChatIn(BaseModel):
    message: str


class AuditIn(BaseModel):
    jd_text: str


# ---------------------------------------------------------------------------
# Health / meta
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, Any]:
    try:
        import sentence_transformers  # noqa: F401
        encoder = "sentence-transformers available (MiniLM)"
    except ImportError:
        encoder = "sentence-transformers missing - TF-IDF+SVD fallback will be used"
    return {
        "status": "ok",
        "version": app.version,
        "encoder": encoder,
        "default_weights": SIMPLE_WEIGHTS.as_dict(),
        "jobs": len(JOBS),
        "runs": len(RUNS),
    }


@app.get("/skills")
def skills(q: str | None = None, limit: int = 200) -> dict[str, Any]:
    """The skill vocabulary, for autocomplete in the filter UI."""
    ont = get_ontology()
    items = [
        {"key": k, "label": n.canonical, "category": n.category,
         "aliases": n.aliases[:6], "importance": n.importance}
        for k, n in ont.nodes.items()
    ]
    if q:
        needle = q.lower()
        items = [i for i in items
                 if needle in i["key"] or needle in i["label"].lower()
                 or any(needle in a for a in i["aliases"])]
    items.sort(key=lambda i: i["label"])
    return {"count": len(items), "skills": items[:limit]}


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
@app.post("/jobs")
def create_job(body: JobIn) -> dict[str, Any]:
    return _store_job(body.title, body.jd_text)


@app.post("/jobs/upload")
async def create_job_upload(jd: UploadFile = File(...), title: str = Form("")) -> dict[str, Any]:
    import tempfile

    from app.parsing.extract import extract_document

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / Path(jd.filename or "jd.txt").name
        p.write_bytes(await jd.read())
        doc = extract_document(p)
    if not doc.text.strip():
        raise HTTPException(400, f"Could not extract text from '{jd.filename}'. "
                                 f"{'; '.join(doc.warnings)}")
    return _store_job(title, doc.text)


@app.get("/jobs")
def list_jobs() -> dict[str, Any]:
    return {"count": len(JOBS), "jobs": [
        {k: v for k, v in j.items() if k != "jd_text"} for j in JOBS.values()]}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    return _get_job(job_id)


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str) -> dict[str, Any]:
    _get_job(job_id)
    JOBS.pop(job_id)
    return {"deleted": job_id}


@app.post("/jd/audit")
def jd_audit(body: AuditIn) -> dict[str, Any]:
    jd = parse_jd(body.jd_text)
    return {"job_description": jd.to_dict(), "audit": audit_jd(jd)}


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------
def _finish(engine: ShortlistEngine, job_id: str | None, explain_top: int,
            verbose: bool, failures=None) -> dict[str, Any]:
    payload = engine.result(explain_top=explain_top, verbose=verbose)
    run_id = _store_run(engine, job_id)
    payload["run_id"] = run_id
    payload["job_id"] = job_id
    payload["session_id"] = run_id          # backwards-compatible alias
    if failures:
        payload["failed_files"] = failures
    return payload


@app.post("/rank")
def rank(body: RankRequest) -> dict[str, Any]:
    if not body.resumes:
        raise HTTPException(400, "No resumes supplied.")
    jd_text = body.jd_text
    job_id = body.job_id
    if job_id:
        jd_text = _get_job(job_id)["jd_text"]
    if not jd_text:
        raise HTTPException(400, "Supply either jd_text or a job_id.")

    engine = ShortlistEngine.from_text(jd_text, {r.name: r.text for r in body.resumes})
    sw = SimpleWeights(**{**SIMPLE_WEIGHTS.as_dict(), **(body.weights or {})}) \
        if body.weights else SIMPLE_WEIGHTS
    engine.run(weights=sw.to_weights(), explain_top=body.explain_top)
    return _finish(engine, job_id, body.explain_top, body.verbose)


@app.post("/rank/upload")
async def rank_upload(
    jd: UploadFile = File(...),
    resumes: list[UploadFile] = File(...),
    explain_top: int = Form(3),
    verbose: bool = Form(False),
) -> dict[str, Any]:
    import tempfile

    from app.parsing.extract import extract_document

    if not resumes:
        raise HTTPException(400, "No resumes supplied.")

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / Path(jd.filename or "jd.txt").name
        p.write_bytes(await jd.read())
        jd_obj = parse_jd(extract_document(p))

    parsed, failures = await _parse_uploads(resumes)
    if not parsed:
        raise HTTPException(400, {"message": "No resume could be parsed.", "failures": failures})

    engine = ShortlistEngine(jd_obj, parsed)
    engine.run(explain_top=explain_top)
    return _finish(engine, None, explain_top, verbose, failures)


@app.post("/jobs/{job_id}/rank/upload")
async def rank_upload_for_job(
    job_id: str,
    resumes: list[UploadFile] = File(...),
    explain_top: int = Form(3),
    verbose: bool = Form(False),
) -> dict[str, Any]:
    """The main path: a saved job + a folder of resume files."""
    job = _get_job(job_id)
    parsed, failures = await _parse_uploads(resumes)
    if not parsed:
        raise HTTPException(400, {"message": "No resume could be parsed.", "failures": failures})

    engine = ShortlistEngine(parse_jd(job["jd_text"]), parsed)
    engine.run(explain_top=explain_top)
    return _finish(engine, job_id, explain_top, verbose, failures)


# ---------------------------------------------------------------------------
# Reading a run
# ---------------------------------------------------------------------------
@app.get("/runs")
def list_runs() -> dict[str, Any]:
    return {"count": len(RUN_META), "runs": list(RUN_META.values())}


@app.get("/runs/{run_id}")
def get_run(run_id: str, verbose: bool = False,
            collapse_duplicates: bool = True) -> dict[str, Any]:
    """The ranking.

    `collapse_duplicates` (default true) hides extra copies of the same person -
    the same resume submitted as .pdf and .docx, or a re-submission. Pass false
    to see every uploaded file as its own row.
    """
    engine = _get_run(run_id)
    payload = engine.result(verbose=verbose)
    payload["run_id"] = run_id
    payload["duplicate_summary"] = engine.dedupe()
    if collapse_duplicates:
        unique = engine.unique_candidates()
        payload["ranking"] = [
            {**c.to_dict(verbose=verbose), "rank": i}
            for i, c in enumerate(unique, start=1)
        ]
        payload["collapsed_duplicates"] = len(engine.candidates) - len(unique)
    return payload


@app.get("/runs/{run_id}/matrix")
def get_matrix(run_id: str, include_preferred: bool = True) -> dict[str, Any]:
    """Candidate x skill grid: green tick / amber partial / red cross per cell."""
    return _get_run(run_id).matrix(include_preferred)


@app.get("/runs/{run_id}/candidates/{who}")
def get_candidate(run_id: str, who: str) -> dict[str, Any]:
    """Per-candidate skills page: skill, semantic and keyword scores + evidence."""
    detail = _get_run(run_id).detail(who)
    if detail is None:
        raise HTTPException(404, f"No candidate matching '{who}' in this run.")
    return detail


@app.get("/runs/{run_id}/top")
def get_top(run_id: str, n: int = 3) -> dict[str, Any]:
    """Top-N with every pairwise comparison explained."""
    return _get_run(run_id).top_comparisons(max(2, min(n, 10)))


@app.get("/runs/{run_id}/charts")
def get_charts(run_id: str, top_n: int = 10) -> dict[str, Any]:
    return _get_run(run_id).charts(top_n)


@app.get("/runs/{run_id}/candidates/{who}/timeline")
def get_timeline(run_id: str, who: str) -> dict[str, Any]:
    """Dated history of one candidate + the date-based integrity checks.

    `entries` is ready to draw as a Gantt/timeline; `overlaps` marks the pairs
    that run at the same time, which is what the date-overlap flag fires on.
    """
    payload = _get_run(run_id).timeline(who)
    if payload is None:
        raise HTTPException(404, f"No candidate matching '{who}' in this run.")
    return payload


@app.get("/runs/{run_id}/duplicates")
def get_duplicates(run_id: str) -> dict[str, Any]:
    """Which uploaded files are the same person.

    Every copy is still scored (removing one before scoring would change BM25's
    IDF and the semantic calibration), but the UI can collapse them so one
    candidate does not occupy four rows of the shortlist.
    """
    return _get_run(run_id).dedupe()


@app.get("/runs/{run_id}/flags")
def get_flags(run_id: str) -> dict[str, Any]:
    flagged = _get_run(run_id).flagged()
    return {"flagged_count": len(flagged), "candidates": flagged}


@app.post("/runs/{run_id}/weights")
def set_weights(run_id: str, body: WeightsIn) -> dict[str, Any]:
    """Move the keyword / semantic / experience sliders and re-rank.

    Cheap - the parse and the embeddings are reused, only the fusion changes.
    """
    engine = _get_run(run_id)
    before = {c.resume.doc_id: c.rank for c in engine.candidates}
    engine.reweight(keyword=body.keyword, semantic=body.semantic,
                    experience=body.experience)

    movements = [
        {"candidate": c.resume.name, "from": before[c.resume.doc_id],
         "to": c.rank, "delta": before[c.resume.doc_id] - c.rank}
        for c in engine.candidates
        if c.resume.doc_id in before and before[c.resume.doc_id] != c.rank
    ]
    movements.sort(key=lambda m: -abs(m["delta"]))

    payload = engine.result(explain_top=body.explain_top)
    payload["run_id"] = run_id
    payload["movements"] = movements
    return payload


@app.post("/runs/{run_id}/filter")
def filter_run(run_id: str, body: FilterIn) -> dict[str, Any]:
    """Filter the pool. Ranks are NOT recomputed.

    If a recruiter filters to '2+ years' they still want to see that someone was
    #3 out of everyone, not #1 out of the four survivors.
    """
    engine = _get_run(run_id)
    f = Filters(**body.model_dump())
    kept = engine.filtered(f)
    return {
        "run_id": run_id,
        "filters": f.describe(),
        "matched": len(kept),
        "pool_size": len(engine.candidates),
        "results": [c.to_dict() for c in kept],
    }


@app.post("/runs/{run_id}/compare")
def compare(run_id: str, body: CompareIn) -> dict[str, Any]:
    engine = _get_run(run_id)
    a, b = engine.find(body.a), engine.find(body.b)
    if a is None or b is None:
        raise HTTPException(404, f"No candidate matching '{body.a if a is None else body.b}'.")
    from app.matching.explain import compare_candidates
    return {
        "question": f"Why is {a.resume.name} ranked above {b.resume.name}?",
        "answer": compare_candidates(a, b, engine.jd),
        "a": a.to_dict(),
        "b": b.to_dict(),
    }


@app.post("/runs/{run_id}/chat")
def chat(run_id: str, body: ChatIn) -> dict[str, Any]:
    """Recruiter chat. Rule-routed over the score trace - no LLM, no API key.

    Handles comparisons, single-candidate explanations, "who has <skill>",
    "who is missing <skill>", experience filters, pool gaps, flags, confidence,
    and free-text wishes ("I want someone who has deployed to production"),
    which re-rank the pool against the JD plus that requirement.
    """
    engine = _get_run(run_id)
    reply = engine.chat(body.message)
    reply["run_id"] = run_id
    return reply


# ---------------------------------------------------------------------------
# PDF downloads
# ---------------------------------------------------------------------------
_REPORTS = {
    "ranked_list": (ranked_list_pdf, "shortlist"),
    "top_explanations": (top_explanations_pdf, "top-candidates"),
    "skill_gap": (skill_gap_pdf, "skill-gap"),
}


@app.get("/runs/{run_id}/report/{kind}.pdf")
def download_report(run_id: str, kind: str, n: int = 3) -> Response:
    engine = _get_run(run_id)
    if kind not in _REPORTS:
        raise HTTPException(404, f"Unknown report '{kind}'. "
                                 f"Available: {', '.join(_REPORTS)}")
    fn, slug = _REPORTS[kind]
    pdf = fn(engine, n) if kind == "top_explanations" else fn(engine)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in engine.jd.title)[:40]
    filename = f"{slug}-{safe}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/runs/{run_id}/report/ranked_list.pdf")
def download_filtered_report(run_id: str, body: FilterIn) -> Response:
    """Same PDF, but of a filtered view."""
    engine = _get_run(run_id)
    f = Filters(**body.model_dump())
    kept = engine.filtered(f)
    note = "filtered: " + "; ".join(f.describe()) if f.describe() else ""
    pdf = ranked_list_pdf(engine, candidates=kept, filter_note=note)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="shortlist-filtered.pdf"'})


# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------
@app.post("/parse/resume")
async def parse_one(file: UploadFile = File(...)) -> dict[str, Any]:
    """See exactly what the parser got out of one file."""
    parsed, failures = await _parse_uploads([file])
    if not parsed:
        raise HTTPException(400, {"message": "Could not parse.", "failures": failures})
    r = parsed[0]
    out = r.to_dict()
    out["chunks"] = [{"section": c.section, "text": c.text} for c in r.chunks[:40]]
    return out
