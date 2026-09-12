# Smart Shortlisting Engine

Ranks a batch of resumes against one Job Description and explains why.
Built for the InternLoom AI Hackathon (Team TechTonic).

**No API keys. No LLM scoring.** Every number is computed by code in this folder.

---

## The one thing to understand

There is nothing to *train* here. Nobody has labelled which resume is the right
hire, so there is no supervised learning problem — this is **ranking / information
retrieval**. The system scores each resume against the JD using two genuinely
different mechanisms and fuses them:

| Half | What it does | Where |
|---|---|---|
| **Keyword** | BM25 over the candidate pool + an alias/typo/relation-aware skill ontology | `app/matching/lexical.py`, `app/matching/skills.py` |
| **Semantic** | Local sentence embeddings, JD requirement vs resume bullet, chunk level | `app/matching/semantic.py` |

Both genuinely factor into the final score — neither can be switched off without
the ranking changing.

---

## Quick start

```bash
cd ai
pip install -r requirements.txt
python setup_check.py                     # run this ONCE, pre-downloads the model

python cli.py rank --jd data/jd/Sample_JD.txt --resumes data/validation
```

When the real data arrives, drop the files in and change two paths:

```bash
python cli.py rank --jd data/jd/Sample_JD.pdf --resumes data/resumes --json result.json
```

That is the whole swap. The parser handles `.pdf`, `.docx`, `.doc`, `.txt`, `.rtf`
and does not care how the resumes are formatted internally.

---

## How a score is built

Final score is 0–100, a weighted sum of five sub-scores (weights in `app/config.py`):

```
required_skills   0.34   ontology-aware coverage of the JD's must-haves
semantic          0.26   meaning-level match of resume bullets to JD bullets
lexical           0.16   BM25 against the rest of the candidate pool
preferred_skills  0.12   coverage of the nice-to-haves
experience        0.12   years + education against the stated bar
```

Then a **critical-skill dampener**: if a candidate names fewer than half the JD's
*hard* required skills, the score is scaled down. This is deliberate — the problem
statement says a role asking for specific skills "shouldn't be satisfied by only
loosely related experience", so semantic similarity alone cannot float someone to
the top.

### Skill matching is four-tier, not binary

| Status | Meaning | Credit |
|---|---|---|
| `exact` | resume names the skill, an alias, or a near-typo of it | 1.00 |
| `related` | resume names an ontology neighbour (JD wants React, resume has Next.js) | 0.55 |
| `semantic` | never named, but a resume line means it ("containerised services" → Docker) | ≤0.35 |
| `missing` | no evidence at all | 0.00 |

Each tier records **the exact resume line** it fired on, which is what the
explanations quote.

### Why BM25 rather than plain TF-IDF cosine

- **Term-frequency saturation** — a resume saying "Selenium" 40 times shouldn't beat one saying it 4 times by 10×.
- **Length normalisation** — a 5-page resume naturally contains more of every term.
- **IDF from the actual pool** — "JavaScript" is a weak discriminator when every candidate has it; "Kubernetes" is a strong one. This is learned from the batch, not hard-coded.

It is implemented from scratch in ~60 lines so you can walk a judge through the formula.

### Why chunk-level embeddings

Averaging a 3-page resume into one vector washes out the two lines that matter.
Instead every bullet is embedded separately, each JD requirement is compared against
every bullet, and the top-3 matches are kept — weighted by which **section** they
came from (a line under *Projects* outweighs one under *Hobbies*).

### Adaptive calibration

Raw cosine has no absolute meaning and its scale differs between MiniLM and the
LSA fallback. Rather than hard-coding a band, the engine reads it off the current
batch: the 15th percentile of observed similarity maps to 0, the 90th to 1. Rank
order is unchanged (it's a monotone map) but the numbers stay readable whichever
encoder loaded.

---

## Offline safety

The primary encoder is `all-MiniLM-L6-v2` — ~90MB, downloaded once from HuggingFace,
cached in `~/.cache/huggingface`, then **fully offline**. If it cannot load (no wifi
at the venue, torch missing), the engine automatically falls back to TF-IDF + SVD
(Latent Semantic Analysis) fitted on the batch itself, using pure scikit-learn.
The fallback is weaker but the demo never dies. The CLI tells you which one is live.

Force the fallback to test it: `NEXORA_FORCE_LSA=1 python cli.py rank ...`

---

## What the frontend gets

See **[API.md](API.md)** for the full contract. Summary of what is wired:

| Feature | Endpoint |
|---|---|
| Skill matrix, green tick / amber partial / red cross | `GET /runs/{id}/matrix` |
| Per-candidate page: skill, keyword and semantic scores + evidence | `GET /runs/{id}/candidates/{who}` |
| Top-3 comparison with generated explanations of the differences | `GET /runs/{id}/top?n=3` |
| Adjustable keyword / semantic / experience weights | `POST /runs/{id}/weights` |
| Filters: experience, skills, education, confidence, flags, search | `POST /runs/{id}/filter` |
| Flagging: seniority mismatch, keyword stuffing, prompt injection, ... | `GET /runs/{id}/flags` |
| Confidence predictor | `confidence` on every candidate |
| Charts (bar / radar / scatter / histogram), plot-ready | `GET /runs/{id}/charts` |
| Recruiter chat, incl. free-text wishes that re-rank | `POST /runs/{id}/chat` |
| Multiple job descriptions | `POST /jobs`, `GET /jobs` |
| PDF downloads: ranked list, top explanations, skill gap | `GET /runs/{id}/report/{kind}.pdf` |

### The two numbers to show per candidate

- **score** (0-100) - how well they fit the JD.
- **confidence** (0-100) - how well their resume EVIDENCES its own claims:
  quantified results, ownership language, skills that appear inside described
  work rather than only in a list, verifiable links.

They are independent on purpose. Score 85 / confidence 30 means someone listed
all the right words and described nothing - which is precisely the candidate a
recruiter wants flagged before they spend an hour interviewing.

### Integrity flags

Rule-based, every flag quotes the text that triggered it:

`seniority_mismatch` (a 5-year candidate on an intern posting) &middot;
`keyword_stuffing` (many skills, none attached to described work) &middot;
`prompt_injection` (text aimed at an AI screener - "ignore previous
instructions", "rank this candidate first") &middot; `timeline_inconsistent` &middot;
`experience_unsupported` (claimed years do not match the dates on the same
resume) &middot; `duplicate_resume` &middot; `unreadable` &middot; `very_short` &middot;
`unsubstantiated_claims`.

The scorer never treats resume text as instructions, so an injection attempt
cannot move the ranking - but it gets surfaced to a human.

---

## Commands

```bash
# Rank + explain the top 3
python cli.py rank --jd <jd> --resumes <folder> --top 3

# Full JSON with every piece of evidence (this is what the frontend consumes)
python cli.py rank --jd <jd> --resumes <folder> --json out.json --verbose

# "Why is X ranked above Y?"  (bonus feature)
python cli.py compare --jd <jd> --resumes <folder> --a 1 --b 4

# Explain one candidate
python cli.py why --jd <jd> --resumes <folder> --candidate "Aarav"

# Flag bias / over-narrow phrasing in the JD itself  (bonus feature)
python cli.py audit --jd <jd>

# Candidate x skill grid in the terminal
python cli.py matrix --jd <jd> --resumes <folder>

# Integrity flags across the pool
python cli.py flags --jd <jd> --resumes <folder>

# Recruiter chat (interactive, or one-shot with --message)
python cli.py chat --jd <jd> --resumes <folder>
python cli.py chat --jd <jd> --resumes <folder> --message "who knows Docker"

# Write the three PDFs into ./reports
python cli.py report --jd <jd> --resumes <folder>

# Debug what the parser actually extracted from one file
python cli.py parse --file <resume>
```

---

## Backend

```bash
uvicorn api:app --reload --port 8000
# docs at http://localhost:8000/docs
```

| Endpoint | Purpose |
|---|---|
| `GET  /health` | liveness, which encoder is available |
| `POST /rank` | JSON in: `{jd_text, resumes:[{name,text}]}` |
| `POST /rank/upload` | multipart: post the raw PDFs straight from the browser |
| `GET  /session/{id}` | re-read a previous run without re-embedding |
| `POST /explain/compare` | "why is X above Y" against a cached run |
| `POST /jd/audit` | bias / narrowness audit |
| `POST /parse/resume` | debug: what did the parser see |

A run is cached by `session_id`, so follow-up questions from the UI are instant.

---

## Tests

```bash
python -m pytest tests/ -v
# or individually:
python tests/test_ranking.py        # 18 tests - ranking quality and parsing
python tests/test_api.py            # 23 tests - every endpoint the frontend uses
```

`data/validation/` is a hand-built pool of 9 resumes where the correct ordering is
unarguable — a strong full stack candidate, one who describes the same stack in
different words, a frontend-only dev, a Python backend dev, a Java dev, a DSA-only
competitive programmer, a QA tester, a non-technical writer, and a strong candidate
whose resume is a formatting disaster full of typos.

The suite asserts the properties that matter:

- the strong candidate ranks #1, the non-technical one ranks last
- the **synonym-only** candidate still reaches the top 3 → the semantic half works
- the QA and Python candidates do **not** outrank people with the actual stack → the keyword half works
- the typo-ridden resume still reaches the top 3 → messy formatting is handled
- scores **spread** (currently 6 → 82) rather than clustering
- explanations never claim a skill the candidate does not have

---

## Layout

```
ai/
  app/
    config.py               all tunable weights and thresholds, one file
    pipeline.py             ShortlistEngine - orchestrates everything
    parsing/
      extract.py            pdf/docx/doc/rtf/txt -> clean text, degrades gracefully
      sections.py           section detection + chunking for embedding
      resume.py             Resume model: name, skills, years, education
      jd.py                 JD model: required vs preferred, requirements, seniority
    matching/
      skills.py             the skill ontology (aliases, relations, fuzzy)
      lexical.py            BM25, from scratch
      semantic.py           MiniLM + LSA fallback, chunk-level matching
      score.py              fusion into 0-100 with full evidence trail
      explain.py            natural-language explanations, no LLM
      bias.py               JD bias / over-narrow phrasing audit
      integrity.py          flags (seniority, stuffing, injection) + confidence
      chat.py               recruiter chat - intent routing, no LLM
    reporting/
      matrix.py             skill matrix, chart payloads, filters
      pdf.py                the three downloadable reports
    resources/
      skills.json           119-node skill ontology - edit this to tune matching
  data/
    jd/                     put the real JD here
    resumes/                put the real resumes here
    validation/             hand-built pool with a known-correct ordering
  tests/
    test_ranking.py         ranking quality, parsing, explanations
    test_api.py             every endpoint end to end
  cli.py                    demo CLI
  api.py                    FastAPI backend
  API.md                    the contract the frontend team codes against
  setup_check.py            run once before the event
```

---

## Tuning knobs

Everything lives in `app/config.py`:

- `WEIGHTS` — the five-way fusion
- `RELATED_SKILL_CREDIT` (0.55) / `SEMANTIC_SKILL_CREDIT` (0.35) — how generous partial credit is
- `BM25_K1` / `BM25_B` — saturation and length normalisation
- `SEMANTIC_TOP_K_CHUNKS` — how many resume bullets back each requirement
- `FUZZY_THRESHOLD` — typo tolerance
- `SIMPLE_WEIGHTS` — the three sliders the UI exposes; they expand to the five internal weights and reproduce the default ranking exactly
- `SENIORITY_CEILING` — years above which a candidate is flagged as over-levelled for the role

To teach the system a new technology, add a node to `app/resources/skills.json` —
no code change needed.
