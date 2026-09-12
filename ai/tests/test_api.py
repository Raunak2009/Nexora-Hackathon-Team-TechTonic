"""End-to-end tests for the API surface the frontend consumes.

Uses FastAPI's TestClient, so no server needs to be running.

    python tests/test_api.py        (or: python -m pytest tests/ -v)
"""

from __future__ import annotations

import sys
from pathlib import Path

AI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AI_DIR))

from fastapi.testclient import TestClient    # noqa: E402

import api                                   # noqa: E402

client = TestClient(api.app)

JD_PATH = AI_DIR / "data" / "jd" / "Sample_JD.txt"
VALIDATION = AI_DIR / "data" / "validation"

_STATE: dict = {}


def setup() -> dict:
    """Create a job and rank the validation pool against it, once."""
    if _STATE:
        return _STATE

    job = client.post("/jobs", json={
        "title": "Junior Full Stack Developer Intern",
        "jd_text": JD_PATH.read_text(encoding="utf-8"),
    })
    assert job.status_code == 200, job.text
    job_id = job.json()["job_id"]

    files = [("resumes", (p.name, p.read_bytes(), "text/plain"))
             for p in sorted(VALIDATION.glob("*.txt"))]
    run = client.post(f"/jobs/{job_id}/rank/upload", files=files,
                      data={"explain_top": "3"})
    assert run.status_code == 200, run.text
    body = run.json()

    _STATE.update({"job_id": job_id, "run_id": body["run_id"], "body": body})
    return _STATE


# ---------------------------------------------------------------------------
def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert set(r.json()["default_weights"]) == {"keyword", "semantic", "experience"}


def test_job_creation_includes_bias_audit():
    job_id = setup()["job_id"]
    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    audit = r.json()["bias_audit"]
    assert audit["flag_count"] > 0
    assert {f["category"] for f in audit["flags"]} & {"pedigree", "academic-cutoff"}


def test_rank_returns_ranked_pool_with_both_scores():
    body = setup()["body"]
    ranking = body["ranking"]
    assert len(ranking) == 9
    assert ranking[0]["rank"] == 1
    for row in ranking:
        assert 0 <= row["keyword_score"] <= 100
        assert 0 <= row["semantic_score"] <= 100
        assert row["confidence"] is not None
    scores = [r["score"] for r in ranking]
    assert scores == sorted(scores, reverse=True)


def test_top3_explanations_present():
    body = setup()["body"]
    assert len(body["top_explanations"]) == 3
    for e in body["top_explanations"]:
        assert e["explanation"]
        assert "missing_skills" in e


def test_matrix_has_a_cell_per_candidate_per_skill():
    run_id = setup()["run_id"]
    m = client.get(f"/runs/{run_id}/matrix").json()
    assert len(m["rows"]) == 9
    n_cols = len(m["columns"])
    for row in m["rows"]:
        assert len(row["cells"]) == n_cols
        for cell in row["cells"]:
            assert cell["colour"] in {"green", "amber", "red"}
            assert cell["symbol"] in {"check", "tilde", "cross"}
    assert m["pool_coverage"]


def test_matrix_ticks_agree_with_the_ranking():
    run_id = setup()["run_id"]
    m = client.get(f"/runs/{run_id}/matrix").json()
    body = client.get(f"/runs/{run_id}").json()
    by_doc = {r["doc_id"]: r for r in body["ranking"]}
    for row in m["rows"]:
        green = {c["skill"] for c in row["cells"]
                 if c["status"] == "exact" and c["kind"] == "required"}
        listed = set(by_doc[row["doc_id"]]["matched_required_skills"])
        assert green <= listed, f"{row['candidate']}: matrix ticks not in ranking"


def test_candidate_detail_page():
    run_id = setup()["run_id"]
    d = client.get(f"/runs/{run_id}/candidates/1").json()
    for key in ("scores", "required_skills", "semantic_evidence",
                "confidence", "integrity_flags", "explanation"):
        assert key in d, f"missing {key}"
    assert set(d["scores"]) >= {"final", "skill", "keyword", "semantic"}


def test_candidate_detail_404s_cleanly():
    run_id = setup()["run_id"]
    assert client.get(f"/runs/{run_id}/candidates/nobody-by-that-name").status_code == 404


def test_top_comparison_page():
    run_id = setup()["run_id"]
    t = client.get(f"/runs/{run_id}/top?n=3").json()
    assert len(t["candidates"]) == 3
    assert len(t["pairwise"]) == 3           # 3 choose 2
    for p in t["pairwise"]:
        assert p["explanation"]
        assert "only_a_has" in p and "subscore_deltas" in p


def test_weight_sliders_change_the_ranking():
    run_id = setup()["run_id"]
    base = client.get(f"/runs/{run_id}").json()["ranking"]

    semantic_heavy = client.post(f"/runs/{run_id}/weights",
                                 json={"keyword": 0.1, "semantic": 0.8, "experience": 0.1}).json()
    assert semantic_heavy["engine"]["slider_weights"]["semantic"] > 0.7
    assert semantic_heavy["ranking"][0]["score"] != base[0]["score"]

    # Put them back so later tests see the default ranking.
    restored = client.post(f"/runs/{run_id}/weights",
                           json={"keyword": 0.62, "semantic": 0.26, "experience": 0.12}).json()
    assert [r["doc_id"] for r in restored["ranking"]] == [r["doc_id"] for r in base]


def test_filter_keeps_pool_wide_ranks():
    run_id = setup()["run_id"]
    r = client.post(f"/runs/{run_id}/filter", json={"min_years": 2}).json()
    assert r["matched"] < r["pool_size"]
    ranks = [x["rank"] for x in r["results"]]
    assert ranks != list(range(1, len(ranks) + 1)) or len(ranks) <= 1


def test_filter_by_skill():
    run_id = setup()["run_id"]
    r = client.post(f"/runs/{run_id}/filter", json={"must_have_skills": ["react"]}).json()
    assert r["matched"] >= 1
    for row in r["results"]:
        combined = row["matched_required_skills"] + row["matched_preferred_skills"]
        assert "React" in combined


def test_flags_endpoint_finds_the_seniority_mismatch():
    run_id = setup()["run_id"]
    r = client.get(f"/runs/{run_id}/flags").json()
    codes = {f["code"] for c in r["candidates"] for f in c["flags"]}
    assert "seniority_mismatch" in codes, (
        "E_java_enterprise has 3+ yrs on an intern role and should be flagged")


def test_charts_are_plot_ready():
    run_id = setup()["run_id"]
    ch = client.get(f"/runs/{run_id}/charts").json()
    for key in ("score_bars", "radar", "keyword_vs_semantic",
                "skill_coverage", "score_distribution"):
        assert key in ch
    bars = ch["score_bars"]
    assert len(bars["labels"]) == len(bars["series"][0]["data"])
    assert len(ch["keyword_vs_semantic"]["points"]) == 9


def test_chat_compare():
    run_id = setup()["run_id"]
    r = client.post(f"/runs/{run_id}/chat",
                    json={"message": "why is Aarav ranked above Anjali?"}).json()
    assert r["intent"] == "compare"
    assert "points" in r["answer"]


def test_chat_who_has():
    run_id = setup()["run_id"]
    r = client.post(f"/runs/{run_id}/chat", json={"message": "who knows Docker?"}).json()
    assert r["intent"] == "who_has"
    assert r["candidates"]


def test_chat_free_text_requirement_reranks():
    run_id = setup()["run_id"]
    r = client.post(f"/runs/{run_id}/chat", json={
        "message": "I want someone who has actually deployed something to production with Docker"
    }).json()
    assert r["intent"] == "add_requirement"
    assert r["reranked"] is True
    assert r["data"]["ranking"]


def test_chat_unknown_is_honest():
    run_id = setup()["run_id"]
    r = client.post(f"/runs/{run_id}/chat",
                    json={"message": "what is the weather in Bengaluru"}).json()
    assert r["intent"] == "unknown"
    assert "can handle" in r["answer"]


def test_all_three_pdfs_download():
    run_id = setup()["run_id"]
    for kind in ("ranked_list", "top_explanations", "skill_gap"):
        r = client.get(f"/runs/{run_id}/report/{kind}.pdf")
        assert r.status_code == 200, f"{kind}: {r.text[:200]}"
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 2000, f"{kind} PDF suspiciously small"


def test_filtered_pdf_downloads():
    run_id = setup()["run_id"]
    r = client.post(f"/runs/{run_id}/report/ranked_list.pdf", json={"min_score": 40})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_skills_vocabulary_for_autocomplete():
    r = client.get("/skills?q=react").json()
    labels = {s["label"] for s in r["skills"]}
    assert "React" in labels and "React Native" in labels


def test_unknown_run_id_is_404_not_500():
    assert client.get("/runs/run_doesnotexist").status_code == 404
    assert client.post("/runs/run_doesnotexist/chat", json={"message": "hi"}).status_code == 404


def test_multiple_jobs_can_coexist():
    setup()
    second = client.post("/jobs", json={
        "title": "Data Analyst Intern",
        "jd_text": "Data Analyst Intern\n\nRequirements\n- Strong SQL and Python.\n"
                   "- Experience with Pandas for data analysis.\n"
                   "- Must be comfortable building dashboards in Power BI.\n",
    }).json()
    assert second["job_id"] != _STATE["job_id"]
    listing = client.get("/jobs").json()
    assert listing["count"] >= 2
    assert "sql" in second["parsed"]["required_skills"][0].lower() or \
           any("SQL" in s for s in second["parsed"]["required_skills"])


if __name__ == "__main__":
    failures = 0
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {name}\n          {exc}")
        except Exception as exc:                        # noqa: BLE001
            failures += 1
            print(f"  ERROR {name}\n          {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
