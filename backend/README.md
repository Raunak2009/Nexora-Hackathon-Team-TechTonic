# backend/

The HTTP service and CLI for the Smart Shortlisting Engine.

```bash
cd backend
pip install -r requirements.txt

uvicorn server:app --reload --port 8000     # the API the frontend calls
python main.py --jd <jd> --resumes <folder> # the CLI demo
python tests/test_backend.py                # 22 tests
```

- **API contract for the frontend:** [`../ai/API.md`](../ai/API.md)
- **Live docs once the server is up:** http://localhost:8000/docs
- **What exists:** http://localhost:8000/ (lists every route)
- **Is it actually working:** http://localhost:8000/ready (runs a real self-test, not just a ping)

---

## Why this folder does not contain the scoring code

`backend/` **wraps** `../ai`. It does not reimplement it.

The alternative — a second, simpler scorer living here — means two pieces of code
that both claim to rank candidates. They drift, and then the API returns one
number while the CLI prints another. That is the failure that kills a demo on a
hackathon clock, and it is very hard to debug at 3am.

So every function the team already wrote against still exists here with the same
name and the same signature, and each one delegates to the engine:

| You call | It still returns | Now backed by |
|---|---|---|
| `parser.parse_resume(path)` | sections dict + `_raw` + `_filename` | multi-format extraction, ontology skill detection |
| `parser.parse_jd(text)` | `required_skills`, `nice_to_have_skills`, `min_years_experience`, `_raw` | heading + bullet-level required/preferred split |
| `matcher.keyword_match(skills, text)` | `(score, matched, missing)` | 119-node skill ontology + fuzzy |
| `matcher.semantic_score(jd, resume)` | float 0–1 | local embeddings, no API key |
| `matcher.score_candidate(jd, resume)` | the same 8 keys | the full hybrid scorer |
| `ranker.rank_candidates(scored)` | sorted, `rank` added | + deterministic tie-break |
| `ranker.explain_top_n(ranked, n)` | one string | + quoted evidence lines |

Nothing that already worked stopped working — `tests/test_backend.py` asserts
each of those signatures explicitly.

**New:** `matcher.score_batch(jd, resumes)` — use this instead of calling
`score_candidate` in a loop. BM25's IDF and the semantic calibration are both
pool-relative ("JavaScript" is a weak signal when every applicant lists it, a
strong one when three do), so scoring one resume at a time throws away
information the engine would otherwise have.

---

## Bugs found in the original drop, and what they did

### 1. `if _name_ == "_main_":` — in all four files

Single underscores. Python never matches that, so `python main.py` ran the
imports and then exited silently. Almost certainly markdown eating the double
underscores as italics somewhere in transit rather than anyone's mistake, but it
was in the code. Fixed everywhere.

### 2. The JD bullet regex matched the wrong characters

```python
bullet_pattern = re.compile(r"^[\-\\u2022]\s(.+)")
```

Inside a raw string, `\\u2022` is a literal backslash-u-2-0-2-2, not `•`. Putting
it inside a character class made the pattern match the characters `\`, `u`, `2`,
`0`. So real bullets parsed inconsistently, and any line beginning with "u" was
treated as one.

### 3. `kw_score = req_score or pref_score`

`0.0 or x` evaluates to `x` in Python. A candidate who matched **none** of the
required skills silently got scored on their nice-to-haves instead — exactly
backwards, and it would have quietly promoted weak candidates into the top 3.
There is a regression test for this now.

### 4. `keyword_match([], text)` returned `1.0`

If the JD parser found no skills, every candidate got a perfect keyword score.
"We found nothing to check" should not look like "passed everything." It returns
`0.0` now.

### 5. The model loaded at import time, and only `ImportError` was caught

```python
try:
    from sentence_transformers import SentenceTransformer
    _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
except ImportError:
    ...
```

If the package was installed but the model could not be fetched — venue wifi,
HuggingFace slow, disk full — the real exception is `OSError`/`HTTPError`, which
was not caught. `import matcher` would crash the entire backend. The encoder is
built lazily now and any failure falls back to the local path with a note you
can see on `/health` and in the CLI banner.

### 6. TF-IDF fitted on two documents

```python
TfidfVectorizer().fit_transform([jd_text, resume_text])
```

IDF over a corpus of size 2 carries essentially no information — every term has
a document frequency of 1 or 2. The "fallback" was close to raw term overlap.
It now fits across the whole candidate pool.

### 7. Whole-document embeddings

The original embedded the entire JD as one vector and the entire resume as
another. Averaging three pages into one 384-dim vector washes out the two lines
that decide the hire — a resume that is 95% React and one line of Node scores
the same as one that genuinely does both. Now every resume bullet is embedded
separately and each JD requirement is matched against the best-fitting bullets.
Same cosine similarity, applied where it discriminates — and it yields the exact
resume line behind each match, which is what the explanations quote.

### 8. Found while wiring this up: terse bullet JDs lost every skill

Not from the original files — this was a bug in my own JD parser that their test
JD exposed. A short, title-cased line like `- Node.js` was being read as a
section header by the shape heuristic, so it never became a requirement. A JD
written as a plain bullet list parsed to zero skills. Fixed, with a regression
test in both suites.

---

## Files

```
backend/
  server.py           uvicorn entry point — mounts ../ai/api.py, adds / and /ready
  main.py             CLI, same flags as the original plus --keyword/--semantic/--top
  parser.py           parse_resume / parse_jd / extract_text / split_into_sections
  matcher.py          keyword_match / semantic_score / score_candidate / score_batch
  ranker.py           rank_candidates / explain_candidate / explain_top_n / explain_difference
  engine_bridge.py    the only file that knows where ../ai lives
  tests/test_backend.py
```

If the repo layout changes, point `NEXORA_AI_DIR` at the folder containing `app/`
and everything keeps working.

---

## Before the event

```bash
cd ../ai && python setup_check.py
```

This pre-downloads the embedding model so the venue's wifi cannot break the demo.
Until you run it, `/health` and the CLI banner will tell you the engine is on the
fallback encoder — rankings are still valid, just weaker.

## Open question for the team

`package.json` pulls in `@supabase/supabase-js`. Nothing in the backend touches
it yet. If the plan is to persist jobs and runs in Supabase rather than the
in-memory store the API currently uses, say so and it is a small change — right
now a server restart loses every run.
