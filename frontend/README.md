# frontend/

The NexHire dashboard. Replit workspace: a React app (`artifacts/nexhire`) and an
Express API (`artifacts/api-server`) that the app calls.

```bash
# 1. the scoring engine (separate terminal, from the repo root)
cd backend && uvicorn server:app --port 8000

# 2. this workspace
cd frontend && pnpm install && pnpm dev
```

## What changed

`artifacts/api-server/src/routes/nexhire.ts` used to serve two hardcoded arrays —
`jobs` and `candidateSeeds` — with invented scores. The original is kept beside it
as `nexhire.mock.ts.bak` for reference.

It now forwards every request to the Python engine through
`artifacts/api-server/src/lib/engine.ts`, and reshapes the responses into the same
`Candidate` / `JobDescription` / `Dashboard` types the React app already reads.
**The UI itself needed no changes.**

Set `ENGINE_URL` if the engine is not on `http://127.0.0.1:8000`.

If the engine is unreachable every route returns **503** with a message saying how
to start it. That is deliberate: with mock data, a dead backend looked exactly
like a working one, which is the worst thing that can happen during judging.

## The flow

```
POST /nexhire/jobs                      { title, jdText }  -> job
POST /nexhire/jobs/:jobId/resumes       multipart `resumes` -> creates the run
GET  /nexhire/dashboard?jobId=...       candidates + counts + bias audit
GET  /nexhire/candidates?jobId=...      supports filters as query params
GET  /nexhire/candidates/:id            full breakdown with evidence
GET  /nexhire/candidates/:id/timeline   dated history + date-overlap checks
GET  /nexhire/jobs/:jobId/matrix        skill grid (green / amber / red)
GET  /nexhire/jobs/:jobId/top?n=3       top-3 with pairwise comparisons
GET  /nexhire/jobs/:jobId/charts        plot-ready payloads
GET  /nexhire/jobs/:jobId/flags         integrity flags
GET  /nexhire/jobs/:jobId/duplicates    same person, multiple files
PATCH /nexhire/jobs/:jobId/weights      re-rank; returns `movements`
POST /nexhire/jobs/:jobId/chat          recruiter chat
POST /nexhire/exports                   -> a PDF URL to download
```

A job has no candidates until resumes are uploaded to it. The dashboard says so
rather than showing placeholder rows.

## Three things worth wiring into the UI

**`encoderNotes`** — non-empty means the engine fell back to its weaker local
encoder (no model download). Rankings are still valid; you want to know before a
judge asks.

**`failedFiles`** — resumes that could not be parsed. Without surfacing these, a
candidate silently disappears from the shortlist.

**`collapsedDuplicates` / `duplicateSummary`** — the same person often appears as
`.pdf`, `.docx`, `.txt` and `.xml`. All copies are scored (removing one would
change BM25's IDF), but only one row is shown. In the supplied data pack this is
220 files → 153 actual people.

## On the `age` field

`Candidate.age` exists in the generated schema and is always `0`. The engine does
not extract age and will not: it is rarely on a resume, screening on it is
unlawful in most jurisdictions, and the product's own JD bias audit flags
employers who do it as a HIGH severity issue. Drop it from the schema and filter
on `yearsExperience`, `education` and `freshersOnly` instead — those are wired.
