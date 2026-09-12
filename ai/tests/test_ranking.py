"""Regression tests for the Smart Shortlisting Engine.

There is no labelled training data for this problem - nobody has told us which
resume is objectively the best. So instead of inventing labels and pretending to
"train", we hand-built a small validation pool in data/validation/ where the
correct ordering is unarguable, and assert the properties that must hold:

  * an obviously strong full stack candidate must outrank an obviously weak one
  * a candidate who describes the same skills in different WORDS must still rank
    near the top (the semantic half is doing its job)
  * a candidate with none of the required skills must not float up on semantic
    similarity alone (the keyword half is doing its job)
  * messy formatting and typos must not sink a strong candidate
  * scores must SPREAD, not cluster - a ranking where everyone scores 61-64 is
    useless to a recruiter

Run:  python -m pytest tests/ -v      (or just: python tests/test_ranking.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

AI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AI_DIR))

from app.parsing.jd import parse_jd            # noqa: E402
from app.parsing.resume import parse_resume    # noqa: E402
from app.pipeline import ShortlistEngine       # noqa: E402

JD_PATH = AI_DIR / "data" / "jd" / "Sample_JD.txt"
VALIDATION = AI_DIR / "data" / "validation"

_ENGINE: ShortlistEngine | None = None


def engine() -> ShortlistEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ShortlistEngine.from_folder(JD_PATH, VALIDATION)
        _ENGINE.run(explain_top=9)
    return _ENGINE


def rank_of(stem: str) -> int:
    for c in engine().candidates:
        if c.resume.path.stem == stem:
            return c.rank
    raise AssertionError(f"{stem} not found in ranking")


def score_of(stem: str) -> float:
    for c in engine().candidates:
        if c.resume.path.stem == stem:
            return c.score
    raise AssertionError(f"{stem} not found in ranking")


# ---------------------------------------------------------------------------
# JD parsing
# ---------------------------------------------------------------------------
def test_jd_extracts_the_real_stack():
    jd = parse_jd(JD_PATH)
    required = set(jd.required_keys)
    for key in ("javascript", "react", "node.js", "rest api", "mongodb", "git", "html", "css"):
        assert key in required, f"JD parser missed required skill: {key}"


def test_jd_separates_preferred_from_required():
    jd = parse_jd(JD_PATH)
    preferred = set(jd.preferred_keys)
    assert "typescript" in preferred or "next.js" in preferred
    assert "docker" in preferred
    # Nothing may be in both buckets.
    assert not (set(jd.required_keys) & preferred)


def test_jd_ignores_company_marketing():
    jd = parse_jd(JD_PATH)
    joined = " ".join(r.text.lower() for r in jd.requirements)
    assert "stipend" not in joined
    assert "mentorship from senior" not in joined


def test_jd_detects_seniority():
    jd = parse_jd(JD_PATH)
    assert jd.seniority == "intern"


# ---------------------------------------------------------------------------
# Ranking quality
# ---------------------------------------------------------------------------
def test_strong_candidate_wins():
    assert rank_of("A_strong_fullstack") == 1


def test_non_technical_candidate_is_last():
    assert rank_of("H_non_technical") == len(engine().candidates)


def test_semantic_half_works_synonyms_rank_high():
    """B never writes 'Node.js' or 'REST APIs' - only 'Express' and 'RESTful
    web services'. A pure keyword system would bury them."""
    assert rank_of("B_synonym_only") <= 3


def test_keyword_half_works_related_experience_does_not_win():
    """G is a competent QA engineer and D a competent Python backend dev, but
    neither has the stack this JD names. They must not outrank candidates who
    actually have it."""
    assert rank_of("G_qa_tester") > rank_of("C_frontend_only")
    assert rank_of("D_backend_python") > rank_of("B_synonym_only")


def test_messy_formatting_does_not_sink_a_strong_candidate():
    """I has typos ('Javascrpit'), no capitalisation and broken section headers,
    but is genuinely a strong full stack candidate."""
    assert rank_of("I_strong_but_messy") <= 3


def test_scores_are_spread_not_clustered():
    scores = [c.score for c in engine().candidates]
    assert max(scores) - min(scores) > 30, f"Ranking is too flat to be useful: {scores}"
    assert max(scores) > 60, "Even the best candidate scores low - check calibration"


def test_ranking_is_stable_across_runs():
    e2 = ShortlistEngine.from_folder(JD_PATH, VALIDATION)
    e2.run()
    a = [c.resume.path.stem for c in engine().candidates]
    b = [c.resume.path.stem for c in e2.candidates]
    assert a == b, "Ranking is not deterministic"


# ---------------------------------------------------------------------------
# Explanations
# ---------------------------------------------------------------------------
def test_explanations_never_claim_a_skill_the_candidate_lacks():
    for c in engine().candidates:
        named = {m.canonical for m in c.required_matches if m.status == "exact"}
        named |= {m.canonical for m in c.preferred_matches if m.status == "exact"}
        text = c.explanation or ""
        if "Also names preferred skills:" in text:
            claimed = text.split("Also names preferred skills:")[1].split(". ")[0].rstrip(".")
            for skill in [s.strip() for s in claimed.replace(" and ", ",").split(",")]:
                if skill and not skill.startswith("(+"):
                    assert skill in named, f"{c.resume.name}: claimed unnamed skill '{skill}'"


def test_top3_explanations_list_gaps():
    for c in engine().candidates[:3]:
        assert c.explanation
        assert ("Missing" in c.explanation) or ("No required skill" in c.explanation)


def test_comparison_answers_a_real_question():
    answer = engine().why_above("A_strong_fullstack", "H_non_technical")
    assert "ranks #1" in answer
    assert "points" in answer


# ---------------------------------------------------------------------------
# Parsing robustness
# ---------------------------------------------------------------------------
def test_names_are_not_section_headers():
    bad = {"skills", "technical skills", "about", "experience", "education", "profile"}
    for c in engine().candidates:
        assert c.resume.name.lower() not in bad, f"Parsed a header as a name: {c.resume.name}"


def test_typo_skill_is_still_found():
    r = parse_resume(VALIDATION / "I_strong_but_messy.txt")
    keys = r.skill_keys
    assert "javascript" in keys, "fuzzy matching failed on 'Javascrpit'"
    assert "react" in keys, "alias matching failed on 'Reactjs'"
    assert "mongodb" in keys, "alias matching failed on 'mongo db'"


def test_experience_is_extracted_from_date_ranges():
    r = parse_resume(VALIDATION / "E_java_enterprise.txt")
    assert r.years_experience >= 1.5, f"got {r.years_experience}"


def test_bias_audit_finds_the_planted_issues():
    from app.matching.bias import audit_jd

    report = audit_jd(parse_jd(JD_PATH))
    categories = {f["category"] for f in report["flags"]}
    assert "pedigree" in categories, "missed 'tier-1 colleges preferred'"
    assert "academic-cutoff" in categories, "missed the CGPA cutoff"



# ---------------------------------------------------------------------------
# Real data pack: XML, deduplication, timeline checks
# ---------------------------------------------------------------------------
REAL_POOL = AI_DIR / "data" / "resumes"


def test_xml_resumes_keep_their_sections():
    """The pack includes structured resume XML. A generic tag-strip would throw
    away the one advantage that format has: its sections are already labelled."""
    xmls = sorted(REAL_POOL.glob("*.xml"))
    assert xmls, "no .xml resumes found in the data pack"
    r = parse_resume(xmls[0])
    found = {s.name for s in r.sections}
    assert {"skills", "experience"} <= found, f"only found {found}"
    assert r.email and r.name != "Unknown Candidate"
    assert r.skills


def test_every_file_in_the_pack_is_readable():
    from app.parsing.extract import extract_folder

    docs = extract_folder(REAL_POOL)
    assert len(docs) >= 200, f"only {len(docs)} files picked up"
    unreadable = [d.path.name for d in docs if not d.ok]
    assert not unreadable, f"unreadable: {unreadable[:5]}"


def test_doc_ids_are_unique():
    """Same resume as .pdf/.docx/.txt/.xml shares a filename stem. A shared
    doc_id also silently shared the semantic matcher's embedding cache."""
    from app.parsing.extract import extract_folder

    resumes = [parse_resume(d) for d in extract_folder(REAL_POOL)]
    ids = [r.doc_id for r in resumes]
    assert len(set(ids)) == len(ids)


def test_dedupe_groups_the_same_person_across_formats():
    from app.matching.dedupe import dedupe_report
    from app.parsing.extract import extract_folder

    resumes = [parse_resume(d) for d in extract_folder(REAL_POOL)]
    rep = dedupe_report(resumes)
    assert rep["duplicate_groups"] > 10
    assert rep["unique_candidates"] < rep["files"]
    biggest = max(rep["groups"], key=lambda g: g["copies"])
    assert biggest["copies"] >= 4


def test_dedupe_does_not_merge_people_who_share_a_placeholder_email():
    """dummy.email@example.com is on twenty DIFFERENT resumes in this pack.
    Merging on email alone would delete nineteen people from the shortlist."""
    from app.matching.dedupe import group_identities, is_placeholder_email
    from app.parsing.extract import extract_folder

    resumes = [parse_resume(d) for d in extract_folder(REAL_POOL)]
    placeholder = [r for r in resumes if is_placeholder_email(r.email)]
    assert len(placeholder) >= 15, "expected the template stubs to be present"

    groups = group_identities(resumes)
    gid = {m.doc_id: g.group_id for g in groups for m in g.members}
    distinct = {gid[r.doc_id] for r in placeholder}
    assert len(distinct) == len(placeholder), (
        f"{len(placeholder)} distinct people collapsed into {len(distinct)} rows")


def test_role_specific_jd_surfaces_its_own_role_from_the_whole_pool():
    """The hard test: rank one JD against all ~220 mixed-role resumes and check
    the right specialism comes out on top."""
    from app.pipeline import ShortlistEngine

    for jd_name, marker in (("SDE_Intern", "sde"),
                            ("Cyber_Security_Intern", "cyber"),
                            ("Data_Scientist_Intern", "data_scientist")):
        engine = ShortlistEngine.from_folder(AI_DIR / "data" / "jd" / f"{jd_name}.txt",
                                             REAL_POOL)
        engine.run()
        top5 = engine.unique_candidates()[:5]
        hits = sum(1 for c in top5 if marker in c.resume.path.name.lower())
        assert hits >= 3, (
            f"{jd_name}: only {hits}/5 of the top candidates are {marker} resumes "
            f"({[c.resume.path.name for c in top5]})")


def test_timeline_detects_overlapping_roles():
    from app.matching.timeline import analyse_timeline
    from app.parsing.extract import ExtractedDocument

    text = (
        "RAHUL SHARMA\nrahul@example.com\n\nEXPERIENCE\n\n"
        "Backend Engineer | Acme Corp | Jan 2023 - Dec 2024\n"
        "- Built REST APIs with Node.js and MongoDB.\n\n"
        "Full Stack Developer | Beta Labs | Jun 2023 - Mar 2025\n"
        "- Built React dashboards.\n\n"
        "Software Engineer | Gamma Inc | Feb 2024 - Present\n"
        "- Maintained microservices.\n\n"
        "EDUCATION\nB.Tech Computer Science | 2021 - 2025\n"
    )
    r = parse_resume(ExtractedDocument(path=Path("overlap.txt"), text=text, method="test"))
    flags, payload = analyse_timeline(r, parse_jd(JD_PATH))
    codes = {f.code for f in flags}
    assert "date_overlap" in codes
    assert payload["overlaps"], "no overlapping pairs recorded"
    assert payload["total_work_months"] > payload["calendar_span_months"]


def test_timeline_does_not_flag_a_clean_history():
    from app.matching.timeline import analyse_timeline
    from app.parsing.extract import ExtractedDocument

    text = (
        "PRIYA SINGH\npriya@example.com\n\nEXPERIENCE\n\n"
        "Intern | Acme | Jun 2023 - Aug 2023\n- Did the work.\n\n"
        "Intern | Beta | Jun 2024 - Aug 2024\n- Did more work.\n\n"
        "EDUCATION\nB.Tech | 2021 - 2025\n"
    )
    r = parse_resume(ExtractedDocument(path=Path("clean.txt"), text=text, method="test"))
    flags, _ = analyse_timeline(r, parse_jd(JD_PATH))
    assert "date_overlap" not in {f.code for f in flags}


def test_employment_gaps_are_never_flagged():
    """Deliberate: gap screening filters out carers, people who were ill and
    career changers - and our own JD bias audit criticises employers for it."""
    from app.matching.timeline import analyse_timeline
    from app.parsing.extract import ExtractedDocument

    text = (
        "ARJUN RAO\narjun@example.com\n\nEXPERIENCE\n\n"
        "Engineer | Acme | Jan 2019 - Dec 2019\n- Work.\n\n"
        "Engineer | Beta | Jan 2024 - Dec 2024\n- Work.\n\n"
        "EDUCATION\nB.Tech | 2015 - 2019\n"
    )
    r = parse_resume(ExtractedDocument(path=Path("gap.txt"), text=text, method="test"))
    flags, _ = analyse_timeline(r, parse_jd(JD_PATH))
    assert not any("gap" in f.code for f in flags)


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
        except Exception as exc:                       # noqa: BLE001
            failures += 1
            print(f"  ERROR {name}\n          {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
