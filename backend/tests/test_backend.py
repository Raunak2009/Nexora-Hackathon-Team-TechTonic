"""Backend tests.

Two jobs:

1. COMPATIBILITY. The original parser/matcher/ranker API must still work
   exactly as written, so nothing anyone already wrote against it breaks.
2. CORRECTNESS. The bugs found in the original drop must stay fixed.

    cd backend && python tests/test_backend.py
    (or: python -m pytest tests/ -v)
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import matcher                                  # noqa: E402
import parser as resume_parser                  # noqa: E402
import ranker                                   # noqa: E402
from engine_bridge import ENGINE_DIR            # noqa: E402

JD_PATH = ENGINE_DIR / "data" / "jd" / "Sample_JD.txt"
VALIDATION = ENGINE_DIR / "data" / "validation"

_CACHE: dict = {}


def ranked():
    if "ranked" not in _CACHE:
        jd = resume_parser.parse_jd_file(str(JD_PATH))
        resumes = [resume_parser.parse_resume(str(p))
                   for p in sorted(VALIDATION.glob("*.txt"))]
        scored = matcher.score_batch(jd, resumes)
        _CACHE["jd"] = jd
        _CACHE["ranked"] = ranker.rank_candidates(scored)
    return _CACHE["ranked"]


def by_file(stem: str):
    for c in ranked():
        if c["filename"].startswith(stem):
            return c
    raise AssertionError(f"{stem} not in ranking")


# ---------------------------------------------------------------------------
# Compatibility with the original API
# ---------------------------------------------------------------------------
def test_parse_resume_returns_the_original_shape():
    r = resume_parser.parse_resume(str(VALIDATION / "A_strong_fullstack.txt"))
    assert "_raw" in r and "_filename" in r
    assert r["_filename"] == "A_strong_fullstack.txt"
    assert isinstance(r["_raw"], str) and len(r["_raw"]) > 100
    # section keys, as before
    assert "skills" in r or "experience" in r


def test_parse_jd_returns_the_original_shape():
    jd = resume_parser.parse_jd(JD_PATH.read_text(encoding="utf-8"))
    for key in ("required_skills", "nice_to_have_skills",
                "min_years_experience", "_raw"):
        assert key in jd, f"missing original key: {key}"
    assert isinstance(jd["required_skills"], list)
    assert isinstance(jd["nice_to_have_skills"], list)


def test_keyword_match_returns_the_original_triple():
    score, matched, missing = matcher.keyword_match(
        ["React", "Node.js", "Kubernetes"],
        "Built a React front end and a Node.js API.")
    assert 0.0 <= score <= 1.0
    assert set(matched) == {"React", "Node.js"}
    assert missing == ["Kubernetes"]
    assert abs(score - 2 / 3) < 1e-9


def test_semantic_score_returns_a_float_0_to_1():
    s = matcher.semantic_score("Node.js backend developer",
                               "Built REST APIs with Express and MongoDB")
    assert isinstance(s, float) and 0.0 <= s <= 1.0


def test_score_candidate_returns_the_original_keys():
    jd = resume_parser.parse_jd_file(str(JD_PATH))
    r = resume_parser.parse_resume(str(VALIDATION / "A_strong_fullstack.txt"))
    out = matcher.score_candidate(jd, r)
    for key in ("filename", "final_score", "keyword_score", "semantic_score",
                "matched_required", "missing_required",
                "matched_preferred", "missing_preferred"):
        assert key in out, f"missing original key: {key}"
    assert 0.0 <= out["final_score"] <= 1.0


def test_rank_candidates_adds_rank_and_sorts():
    rows = ranked()
    assert rows[0]["rank"] == 1
    scores = [c["final_score"] for c in rows]
    assert scores == sorted(scores, reverse=True)


def test_explain_top_n_returns_a_string():
    text = ranker.explain_top_n(ranked(), n=3)
    assert isinstance(text, str) and len(text) > 100


def test_ranker_still_works_on_plain_dicts():
    """Hand-built fixtures (no engine objects) must not crash the explainer."""
    fake = [
        {"filename": "alice.pdf", "final_score": 0.81, "keyword_score": 0.9,
         "semantic_score": 0.7, "matched_required": ["Node.js"],
         "missing_required": [], "matched_preferred": [], "missing_preferred": []},
        {"filename": "bob.pdf", "final_score": 0.55, "keyword_score": 0.5,
         "semantic_score": 0.6, "matched_required": [],
         "missing_required": ["Node.js"], "matched_preferred": [], "missing_preferred": []},
    ]
    out = ranker.rank_candidates(fake)
    assert out[0]["filename"] == "alice.pdf"
    assert "alice.pdf" in ranker.explain_top_n(out, n=2)
    assert isinstance(ranker.explain_difference(out[0], out[1]), str)


# ---------------------------------------------------------------------------
# The bugs from the original drop must stay fixed
# ---------------------------------------------------------------------------
def test_bullet_only_jd_parses_its_skills():
    """Regression: a terse bullet JD used to lose every skill, because a short
    title-cased line like '- Node.js' was read as a section header."""
    jd = resume_parser.parse_jd(
        "Backend Developer\n\n"
        "Required:\n- Node.js\n- MongoDB\n- 2+ years of experience\n\n"
        "Preferred:\n- Docker\n- AWS\n"
    )
    assert "Node.js" in jd["required_skills"]
    assert "MongoDB" in jd["required_skills"]
    assert "Docker" in jd["nice_to_have_skills"]
    assert "AWS" in jd["nice_to_have_skills"]
    assert "Docker" not in jd["required_skills"]
    assert jd["min_years_experience"] == 2


def test_empty_skill_list_does_not_score_1():
    """Regression: `keyword_match([], ...)` returned 1.0, so a JD that failed to
    parse handed every candidate a perfect keyword score."""
    score, matched, missing = matcher.keyword_match([], "anything at all")
    assert score == 0.0
    assert matched == [] and missing == []


def test_zero_required_score_does_not_fall_through_to_preferred():
    """Regression: `req_score or pref_score` - 0.0 is falsy, so a candidate who
    matched NO required skills was silently scored on nice-to-haves instead."""
    jd = resume_parser.parse_jd(
        "Role\n\nRequired:\n- Kubernetes\n- Rust\n\nPreferred:\n- React\n- CSS\n")
    r = resume_parser.parse_resume_text(
        "Frontend developer. Built interfaces with React and CSS.", "front.txt")
    out = matcher.score_candidate(jd, r)
    assert out["missing_required"], "expected the required skills to be missing"
    assert out["keyword_score"] < 0.6, (
        f"keyword score {out['keyword_score']} is too high for a candidate with "
        f"none of the required skills - the preferred-skill fallthrough is back")


def test_importing_matcher_does_not_require_network():
    """Regression: the model used to load at import time and only ImportError
    was caught, so a network failure crashed the whole backend on import."""
    import importlib
    importlib.reload(matcher)
    info = matcher.semantic_backend_info()
    assert "using_transformer" in info and "detail" in info


def test_unreadable_file_does_not_kill_the_batch(tmp_path=None):
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.txt"
        good.write_text((VALIDATION / "A_strong_fullstack.txt").read_text())
        (Path(tmp) / "broken.pdf").write_bytes(b"not really a pdf at all")

        import main
        parsed, failures = main.load_resumes(tmp)
        assert len(parsed) == 1, "the readable resume should still be parsed"
        assert len(failures) == 1, "the broken file should be reported, not silent"


# ---------------------------------------------------------------------------
# Ranking sanity through the backend API
# ---------------------------------------------------------------------------
def test_strong_candidate_ranks_first():
    assert by_file("A_strong")["rank"] == 1


def test_non_technical_ranks_last():
    assert by_file("H_non_technical")["rank"] == len(ranked())


def test_synonym_candidate_is_not_buried():
    """B says 'Express' and 'RESTful web services', never 'Node.js'."""
    assert by_file("B_synonym")["rank"] <= 3


def test_scores_spread():
    scores = [c["final_score"] for c in ranked()]
    assert max(scores) - min(scores) > 0.3, f"too flat: {scores}"


def test_every_row_carries_both_scores_and_confidence():
    for c in ranked():
        assert 0.0 <= c["keyword_score"] <= 1.0
        assert 0.0 <= c["semantic_score"] <= 1.0
        assert c["confidence"] is not None


def test_explanations_quote_real_evidence():
    top = ranked()[0]
    assert top["semantic_evidence"], "no semantic evidence recorded"
    line = top["semantic_evidence"][0]["resume_line"]
    assert line and line[:30] in top["_engine"].resume.raw_text


def test_json_safe_output_is_serialisable():
    import json

    payload = ranker.to_json_safe(ranked())
    json.dumps(payload)                      # must not raise
    assert all(not k.startswith("_") for row in payload for k in row)


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
def test_server_imports_and_exposes_the_routes():
    from fastapi.testclient import TestClient

    import server
    client = TestClient(server.app)

    root = client.get("/")
    assert root.status_code == 200
    body = root.json()
    assert "/jobs" in body["endpoints"]
    assert any("matrix" in p for p in body["endpoints"])

    assert client.get("/health").status_code == 200


def test_ready_endpoint_runs_a_real_self_test():
    from fastapi.testclient import TestClient

    import server
    client = TestClient(server.app)
    body = client.get("/ready").json()
    assert body["ready"] is True, body.get("reason")
    assert body["self_test"]["pool"] == 9
    assert body["self_test"]["spread"] > 30


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
        except Exception as exc:                    # noqa: BLE001
            failures += 1
            print(f"  ERROR {name}\n          {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
