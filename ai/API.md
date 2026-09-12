# API contract — for the frontend team

```bash
cd ai
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

Interactive docs (try every endpoint in the browser): **http://localhost:8000/docs**

CORS is wide open in dev, so a Next.js app on `:3000` can call it directly.

---

## Mental model

- A **job** is one job description. Several can be open at once.
- A **run** is one job scored against one batch of resumes.
- A run is cached server-side by `run_id`. Everything after ranking — the table, the charts, filters, chat, PDFs — reads that cache. **You never re-upload.** Re-ranking after a slider move takes milliseconds because the parse and the embeddings are reused.

---

## The flow

```
POST /jobs                             -> job_id
POST /jobs/{job_id}/rank/upload        -> run_id + full ranking     (multipart, the resume files)
GET  /runs/{run_id}/matrix             -> the tick/cross table
GET  /runs/{run_id}/candidates/{who}   -> one candidate's page
GET  /runs/{run_id}/top?n=3            -> top-3 comparison page
GET  /runs/{run_id}/charts             -> plot-ready payloads
POST /runs/{run_id}/weights            -> move the sliders, re-rank
POST /runs/{run_id}/filter             -> filtered view
POST /runs/{run_id}/chat               -> recruiter chat
GET  /runs/{run_id}/report/{kind}.pdf  -> download
```

`{who}` accepts a rank number (`1`), a candidate name (`Aarav`), a filename, or a `doc_id`. Use `doc_id` in code — it is stable.

---

## Endpoints

### Jobs

| Method | Path | Notes |
|---|---|---|
| `POST` | `/jobs` | `{title, jd_text}` → job + parsed skills + bias audit |
| `POST` | `/jobs/upload` | multipart `jd` file (PDF/DOCX/TXT) + `title` |
| `GET` | `/jobs` | list all |
| `GET` | `/jobs/{job_id}` | one, with `parsed` and `bias_audit` |
| `DELETE` | `/jobs/{job_id}` | remove |
| `POST` | `/jd/audit` | `{jd_text}` → bias audit without saving a job |

`POST /jobs` response:

```jsonc
{
  "job_id": "job_9f2a1c",
  "title": "Junior Full Stack Developer Intern",
  "parsed": {
    "title": "...", "seniority": "intern", "min_years": 0,
    "required_skills": ["JavaScript", "React", "Node.js", "REST APIs", "MongoDB", "Git", "HTML", "CSS"],
    "preferred_skills": ["TypeScript", "Next.js", "Docker", "Unit Testing", "AWS"],
    "requirement_count": 19
  },
  "bias_audit": {
    "flag_count": 3, "high_severity": 1,
    "flags": [{ "category": "pedigree", "severity": "high", "phrase": "tier-1 colleges",
                "context": "...", "why": "...", "suggestion": "..." }],
    "summary": "3 potential issue(s) found ..."
  }
}
```

### Ranking

`POST /jobs/{job_id}/rank/upload` — multipart, field `resumes` repeated once per file, plus `explain_top` (default 3) and `verbose`.

```jsonc
{
  "run_id": "run_4b7e21",
  "job_id": "job_9f2a1c",
  "pool_size": 9,
  "engine": {
    "semantic_encoder": "sentence-transformers/all-MiniLM-L6-v2",
    "slider_weights": { "keyword": 0.62, "semantic": 0.26, "experience": 0.12 },
    "notes": [],                       // non-empty if it fell back to LSA — show this
    "elapsed_seconds": 3.1
  },
  "ranking": [
    {
      "rank": 1,
      "doc_id": "A_strong_fullstack",
      "candidate": "Aarav Menon",
      "file": "A_strong_fullstack.txt",
      "email": "aarav.menon@example.com",
      "score": 86.3,                   // 0-100, this is the ranking number
      "skill_score": 94.0,             // required-skill coverage
      "keyword_score": 91.0,           // skills + BM25 combined
      "semantic_score": 81.0,          // meaning-level match
      "subscores": { "required_skills": 0.94, "preferred_skills": 0.68,
                     "semantic": 0.81, "lexical": 1.0, "experience": 0.75,
                     "keyword": 0.91 },
      "weighted_contributions": { "required_skills": 31.9, "semantic": 21.1, ... },
      "matched_required_skills": ["JavaScript", "React", "Node.js", "..."],
      "missing_required_skills": ["Problem Solving"],
      "matched_preferred_skills": ["Next.js", "Docker", "Unit Testing"],
      "years_experience": 0.2,
      "education": "Bachelor's",
      "confidence": { "score": 79.0, "band": "High",
                      "components": {...}, "reasons": ["4 measurable results", "..."] },
      "integrity_flags": [],
      "flag_level": null,              // null | "low" | "medium" | "high"
      "explanation": "#1 Aarav Menon - 86.3/100 (Strong fit ...)"
    }
  ],
  "top_explanations": [ { "rank": 1, "candidate": "...", "explanation": "...",
                          "matched_skills": [...], "missing_skills": [...] } ],
  "jd_bias_audit": { ... },
  "failed_files": []                   // files that could not be parsed — surface these
}
```

`POST /rank` does the same thing from JSON (`{job_id | jd_text, resumes:[{name, text}]}`) if you already have the text.

### Skill matrix — `GET /runs/{run_id}/matrix`

The tick/cross table. Columns are the JD's skills, required first.

```jsonc
{
  "legend": {
    "exact":    { "symbol": "check", "colour": "green", "label": "Has it" },
    "related":  { "symbol": "tilde", "colour": "amber", "label": "Adjacent skill" },
    "semantic": { "symbol": "tilde", "colour": "amber", "label": "Implied, not named" },
    "missing":  { "symbol": "cross", "colour": "red",   "label": "No evidence" }
  },
  "columns": [{ "key": "react", "label": "React", "kind": "required" }],
  "rows": [{
    "rank": 1, "doc_id": "...", "candidate": "Aarav Menon", "score": 86.3,
    "keyword_score": 91.0, "semantic_score": 81.0, "confidence": 79.0,
    "flag_level": null,
    "required_met": 10, "required_partial": 1, "required_total": 12,
    "cells": [{
      "skill": "React", "key": "react", "kind": "required",
      "status": "exact", "colour": "green", "symbol": "check",
      "credit": 1.0, "importance": 1.0,
      "evidence": "- React front end with Redux state management",   // show on hover
      "section": "projects",
      "reason": "Resume explicitly lists 'React' under projects"
    }]
  }],
  "pool_coverage": [{ "skill": "Node.js", "candidates_with_skill": 2, "pool_coverage_pct": 22.2 }],
  "scarcest_skills": ["Problem Solving", "Teamwork", "Node.js"]
}
```

There are **three** cell states, not two. Amber is real: it means the candidate has an adjacent technology, or a resume line implies the skill without naming it. Painting amber as green overstates the match; painting it red throws away a signal the engine worked to produce.

### Candidate page — `GET /runs/{run_id}/candidates/{who}`

```jsonc
{
  "rank": 1, "candidate": "Aarav Menon", "email": "...", "links": [...],
  "education": "Bachelor's", "years_experience": 0.2,
  "experience_source": "computed from employment date ranges",
  "scores": { "final": 86.3, "skill": 94, "keyword": 91, "semantic": 81,
              "preferred": 68, "lexical_bm25": 100, "experience": 75 },
  "weighted_contributions": { "required_skills": 31.9, "semantic": 21.1, ... },
  "confidence": { "score": 79, "band": "High", "components": {...}, "reasons": [...] },
  "integrity_flags": [],
  "required_skills": [{ "skill": "React", "status": "exact", "credit": 1.0,
                        "evidence": "...", "section": "projects", "reason": "..." }],
  "preferred_skills": [ ... ],
  "semantic_evidence": [{ "jd_requirement": "Design and implement server-side endpoints",
                          "resume_line": "Built REST APIs with Express and MongoDB",
                          "similarity": 0.91, "raw_cosine": 0.58, "section": "experience" }],
  "weakest_requirements": [...],
  "top_bm25_terms": [{ "term": "react", "contribution": 2.41 }],
  "missing_jd_terms": ["mongodb", "jest"],
  "explanation": "...",
  "parse_warnings": []
}
```

### Top-3 comparison — `GET /runs/{run_id}/top?n=3`

`candidates` is the top N, `pairwise` is every pair with an explanation:

```jsonc
{
  "candidates": [ { "rank": 1, "candidate": "...", "score": 86.3, "matched": [...], "missing": [...] } ],
  "pairwise": [{
    "a": "Aarav Menon", "a_rank": 1, "a_score": 86.3,
    "b": "Sanjana K",   "b_rank": 2, "b_score": 69.5,
    "score_gap": 16.8,
    "only_a_has": ["Teamwork"], "only_b_has": [], "both_have": ["React", "Node.js", "..."],
    "subscore_deltas": { "required_skills": 0.0, "semantic": 14.8, "lexical": 1.3, ... },
    "explanation": "Aarav Menon ranks #1 at 86.3 and Sanjana K ranks #2 at 69.5 - a gap of 16.8 points. The biggest driver is semantic, worth +14.8 points to Aarav Menon. ..."
  }]
}
```

### Weights — `POST /runs/{run_id}/weights`

```jsonc
// request — send any subset; they are normalised server-side
{ "keyword": 0.5, "semantic": 0.4, "experience": 0.1 }
```

Returns the same shape as `/runs/{run_id}` plus:

```jsonc
"movements": [{ "candidate": "Nikhil Rao", "from": 3, "to": 2, "delta": 1 }]
```

Animate those. Watching candidates move as the slider drags is the most convincing thing in the demo.

Defaults are `keyword 0.62 / semantic 0.26 / experience 0.12`. These expand to the engine's five internal weights and reproduce its own ranking exactly, so "reset" = send those three numbers.

### Filters — `POST /runs/{run_id}/filter`

```jsonc
{
  "min_score": 40, "min_years": 1, "max_years": 3,
  "must_have_skills": ["react", "node.js"],     // AND
  "any_of_skills": ["aws", "docker"],           // OR
  "min_education": 2,                           // 1 diploma 2 bachelor 3 master 4 phd
  "min_confidence": 50,
  "hide_flagged": false,
  "max_flag_severity": "high",                  // hides candidates with a high-severity flag
  "freshers_only": false,
  "search": "menon"                             // name / file / skills
}
```

→ `{ filters: [...human-readable...], matched, pool_size, results: [...] }`

**Ranks are not recomputed.** A candidate who was #3 in the full pool still shows `"rank": 3` after filtering. That is deliberate — "#1 of the 4 who survived my filter" is a misleading number to act on.

`GET /skills?q=rea` returns the skill vocabulary for the filter's autocomplete.

### Chat — `POST /runs/{run_id}/chat`

```jsonc
{ "message": "why is Aarav ranked above Nikhil?" }
```

```jsonc
{
  "intent": "compare",           // see table below
  "answer": "...",               // render as text
  "candidates": ["Aarav Menon", "Nikhil Rao"],
  "data": { ... },               // intent-specific structured payload
  "reranked": false              // true => data.ranking is a NEW ranking, redraw the table
}
```

| intent | triggered by |
|---|---|
| `compare` | "why is X above Y", "compare X and Y" |
| `explain` | "why is #3 there", "tell me about Sanjana" |
| `who_has` | "who knows Docker", "which candidates have AWS" |
| `who_lacks` | "who is missing MongoDB" |
| `add_requirement` | "I want someone who has deployed to production" → **re-ranks** |
| `filter` | "show me candidates with at least 2 years" |
| `best` | "who should I interview", "top 5" |
| `gaps` | "what is this pool missing" |
| `flags` | "anything suspicious" |
| `confidence` | "who is most convincing" |
| `unknown` | anything else — the answer lists what it *can* do |

`add_requirement` is the one worth demoing: the sentence is parsed exactly like a JD bullet, matched semantically against every resume, and the pool is re-ranked against JD **plus** that wish. `data.movements` shows who moved.

### Charts — `GET /runs/{run_id}/charts?top_n=10`

Five plot-ready payloads: `score_bars` (stacked — segments sum to the final score), `radar` (top 5 across six axes), `keyword_vs_semantic` (scatter, the most interesting one — bottom-right is keyword match with no substance behind it), `skill_coverage` (bar), `score_distribution` (histogram). Each carries `title` and often a `note` you can show as a caption.

### Flags — `GET /runs/{run_id}/flags`

```jsonc
{ "flagged_count": 3, "candidates": [{
    "rank": 6, "candidate": "Sneha Iyer", "flag_level": "medium",
    "flags": [{ "code": "seniority_mismatch", "severity": "medium",
                "title": "3.2 yrs experience on a intern role",
                "detail": "...", "evidence": "stated in resume text" }] }] }
```

Codes: `seniority_mismatch`, `keyword_stuffing`, `skill_density`, `skill_dump_line`, `prompt_injection`, `timeline_inconsistent`, `timeline_future`, `experience_unsupported`, `unsubstantiated_claims`, `unreadable`, `very_short`, `parse_warning`, `no_skills_found`, `duplicate_resume`.

`prompt_injection` is worth a distinct badge — it fires when a resume contains text aimed at an AI screener ("ignore previous instructions", "rank this candidate first"). The scorer never treats resume text as instructions, so the ranking is unaffected, but a human should see it.

### PDFs

```
GET  /runs/{run_id}/report/ranked_list.pdf
GET  /runs/{run_id}/report/top_explanations.pdf?n=3
GET  /runs/{run_id}/report/skill_gap.pdf
POST /runs/{run_id}/report/ranked_list.pdf     // same filter body -> PDF of the filtered view
```

Returns `application/pdf` with `Content-Disposition: attachment`. Easiest frontend handling:

```js
const res  = await fetch(`${API}/runs/${runId}/report/ranked_list.pdf`);
const blob = await res.blob();
const url  = URL.createObjectURL(blob);
Object.assign(document.createElement('a'), { href: url, download: 'shortlist.pdf' }).click();
URL.revokeObjectURL(url);
```

---

## Things worth getting right in the UI

**Show two numbers, not one.** `score` is fit; `confidence` is how well the resume evidences its own claims. They are independent. A candidate with score 85 / confidence 30 listed the right words and described nothing — that is exactly who a recruiter wants flagged before an interview, and it is a genuinely interesting thing to point at during judging.

**Surface `engine.notes`.** If it is non-empty the semantic model failed to load and the engine fell back to TF-IDF+SVD. The ranking is still valid but weaker, and you want to know that during a demo rather than discover it afterwards.

**Surface `failed_files`.** A resume that could not be parsed is silently absent from the ranking otherwise.

**Every cell and every score has evidence behind it.** `cells[].evidence`, `semantic_evidence[].resume_line`, `required_skills[].reason`. Use it — a tooltip that quotes the actual resume line is the difference between a table a judge believes and one they don't.

## On the age filter

You asked for filtering by age. I did not build it, and I'd push back on adding it:

1. Age is not reliably extractable from a resume, so any value would be a guess presented as a fact.
2. Age screening in hiring is unlawful in most jurisdictions, including India for many roles.
3. Your own bias-audit feature flags JDs that screen on age as a **high**-severity issue. Shipping an age filter in the same product is a contradiction a judge will spot in about four seconds, and it undercuts the bonus feature you'd otherwise get credit for.

`min_years` / `max_years` (experience), `min_education`, and `freshers_only` are already there and cover every legitimate version of what an age filter would be used for.
