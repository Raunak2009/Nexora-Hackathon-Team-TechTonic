#!/usr/bin/env python3
"""Entry point for the Smart Shortlisting Engine backend.

    python main.py --jd path/to/jd.pdf --resumes path/to/resumes_folder
    python main.py --jd ... --resumes ... --out results.json
    python main.py --jd ... --resumes ... --keyword 0.7 --semantic 0.3

Loads the JD, parses every resume in the folder, scores them against the JD
(keyword + semantic), ranks them, prints the table, and explains the top 3.

WHAT CHANGED AND WHY
--------------------
1. `if _name_ == "_main_":` -> `if __name__ == "__main__":`. Single underscores
   never match, so the original script did nothing at all when run. It is in
   every file of the original drop, so it was almost certainly markdown eating
   the double underscores as italics rather than anyone's mistake - but it was
   in the code, and it is fixed now.

2. `from parser import ...` at the top of a file that also has a local
   `parser.py` only resolves when your shell happens to be in this directory.
   Now bootstrapped explicitly, so `python backend/main.py` works from
   anywhere in the repo.

3. Candidates are scored as a BATCH, not one at a time. BM25's IDF and the
   semantic calibration are both pool-relative - "JavaScript" is a weak signal
   when every applicant lists it and a strong one when three do. Scoring one
   resume at a time throws that information away.

4. Unreadable files are reported rather than silently skipped. The original
   printed a warning and moved on; it is worth seeing at the end which
   candidates never made it into the ranking at all.

5. Added `--keyword` / `--semantic` weight flags and `--top`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from matcher import score_batch, semantic_backend_info   # noqa: E402
from parser import SUPPORTED_EXTENSIONS, parse_jd_file, parse_resume   # noqa: E402
from ranker import explain_top_n, rank_candidates, to_json_safe   # noqa: E402


def load_jd(jd_path: str) -> dict:
    return parse_jd_file(jd_path)


def load_resumes(resumes_folder: str):
    """Parse every supported file in the folder. Returns (parsed, failures)."""
    folder = Path(resumes_folder)
    if not folder.is_dir():
        raise NotADirectoryError(f"{resumes_folder} is not a folder")

    paths = sorted(
        p for p in folder.rglob("*")
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_EXTENSIONS
        and not p.name.startswith(("~$", "."))
    )

    parsed, failures = [], []
    for path in paths:
        try:
            r = parse_resume(str(path))
            if not str(r.get("_raw", "")).strip():
                failures.append((path.name, "no text could be extracted "
                                            "(scanned image? password protected?)"))
                continue
            parsed.append(r)
        except Exception as exc:                    # noqa: BLE001
            failures.append((path.name, f"{type(exc).__name__}: {exc}"))
    return parsed, failures


def run(jd_path: str, resumes_folder: str, output_json: str | None = None,
        keyword_weight: float = 0.5, semantic_weight: float = 0.5,
        top: int = 3) -> int:
    jd_parsed = load_jd(jd_path)
    resumes_parsed, failures = load_resumes(resumes_folder)

    if not resumes_parsed:
        print("No parseable resumes found - check the folder path and file types.")
        for name, why in failures:
            print(f"  [failed] {name}: {why}")
        return 1

    backend = semantic_backend_info()

    print()
    print("=" * 96)
    print(f"JOB      : {jd_parsed['title']}   (seniority: {jd_parsed['seniority']})")
    print(f"REQUIRED : {', '.join(jd_parsed['required_skills']) or '(none detected)'}")
    print(f"PREFERRED: {', '.join(jd_parsed['nice_to_have_skills']) or '(none)'}")
    print(f"POOL     : {len(resumes_parsed)} resumes")
    print(f"SEMANTIC : {backend['detail']}")
    if not backend["using_transformer"]:
        print("           ! running on the fallback encoder - rankings are still valid,")
        print("           ! but weaker. Run ../ai/setup_check.py to fix before demoing.")
    print(f"WEIGHTS  : keyword {keyword_weight:.2f} / semantic {semantic_weight:.2f}")
    print("=" * 96)

    scored = score_batch(jd_parsed, resumes_parsed, keyword_weight, semantic_weight)
    ranked = rank_candidates(scored)

    print()
    print(f"{'#':>3}  {'CANDIDATE':<24} {'FILE':<26} {'FINAL':>6} {'KEYWD':>6} "
          f"{'SEMANT':>7} {'CONF':>5} {'FLAG':>5}")
    print("-" * 96)
    for c in ranked:
        conf = c.get("confidence") or {}
        flag = {"high": " HIGH", "medium": "  MED", "low": "  low"}.get(c.get("flag_level"), "    -")
        print(f"{c['rank']:>3}  {str(c.get('candidate', ''))[:24]:<24} "
              f"{c['filename'][:26]:<26} {c['final_score']:>6.3f} "
              f"{c['keyword_score']:>6.3f} {c['semantic_score']:>7.3f} "
              f"{conf.get('score', 0):>5.0f} {flag}")

    print()
    print("=" * 96)
    print(f"TOP {top} - WHY")
    print("=" * 96)
    print(explain_top_n(ranked, n=top))

    if failures:
        print()
        print(f"{len(failures)} file(s) could not be read and are NOT in the ranking:")
        for name, why in failures:
            print(f"  - {name}: {why}")

    if output_json:
        payload = {
            "job_description": {k: v for k, v in jd_parsed.items() if not k.startswith("_")},
            "engine": {"semantic_backend": backend,
                       "keyword_weight": keyword_weight,
                       "semantic_weight": semantic_weight},
            "ranking": to_json_safe(ranked),
            "failed_files": [{"file": n, "reason": w} for n, w in failures],
        }
        Path(output_json).write_text(json.dumps(payload, indent=2, default=str),
                                     encoding="utf-8")
        print(f"\nFull ranked results written to {output_json}")

    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Smart Shortlisting Engine")
    ap.add_argument("--jd", required=True,
                    help="Path to the JD file (.txt/.pdf/.docx)")
    ap.add_argument("--resumes", required=True,
                    help="Path to the folder containing resumes")
    ap.add_argument("--out", default=None,
                    help="Write full JSON results here (e.g. results.json)")
    ap.add_argument("--keyword", type=float, default=0.5,
                    help="Keyword weight (default 0.5)")
    ap.add_argument("--semantic", type=float, default=0.5,
                    help="Semantic weight (default 0.5)")
    ap.add_argument("--top", type=int, default=3,
                    help="How many candidates to explain (default 3)")
    args = ap.parse_args()

    raise SystemExit(run(args.jd, args.resumes, args.out,
                         args.keyword, args.semantic, args.top))
