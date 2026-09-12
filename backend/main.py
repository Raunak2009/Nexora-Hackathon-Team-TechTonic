"""
Entry point for the Smart Shortlisting Engine backend.

Usage:
    python main.py --jd path/to/jd.txt --resumes path/to/resumes_folder

Loads the JD, parses every resume in the given folder, scores each one
against the JD (keyword + semantic), ranks them, prints the full ranked
table, and prints detailed explanations for the top 3.
"""

import argparse
import glob
import json
import os

from parser import parse_jd, parse_resume, extract_text
from matcher import score_candidate
from ranker import rank_candidates, explain_top_n

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt")


def load_jd(jd_path: str) -> dict:
    raw_text = extract_text(jd_path)
    return parse_jd(raw_text)


def load_resumes(resumes_folder: str) -> list:
    paths = [
        p for p in glob.glob(os.path.join(resumes_folder, "*"))
        if p.lower().endswith(SUPPORTED_EXTENSIONS)
    ]
    parsed = []
    for path in paths:
        try:
            parsed.append(parse_resume(path))
        except Exception as e:
            print(f"[warn] Skipping {path}: could not parse ({e})")
    return parsed


def run(jd_path: str, resumes_folder: str, output_json: str = None):
    jd_parsed = load_jd(jd_path)
    resumes_parsed = load_resumes(resumes_folder)

    if not resumes_parsed:
        print("No parseable resumes found — check the folder path and file types.")
        return

    scored = [score_candidate(jd_parsed, r) for r in resumes_parsed]
    ranked = rank_candidates(scored)

    print("\n=== Ranked Candidates ===")
    for c in ranked:
        print(f"{c['rank']:>2}. {c['filename']:<30} final={c['final_score']:.3f}  "
              f"keyword={c['keyword_score']:.3f}  semantic={c['semantic_score']:.3f}")

    print("\n=== Top 3 Explanations ===")
    print(explain_top_n(ranked, n=3))

    if output_json:
        with open(output_json, "w") as f:
            json.dump(ranked, f, indent=2)
        print(f"\nFull ranked results written to {output_json}")


if _name_ == "_main_":
    parser_args = argparse.ArgumentParser(description="Smart Shortlisting Engine")
    parser_args.add_argument("--jd", required=True, help="Path to the JD file (.txt/.pdf/.docx)")
    parser_args.add_argument("--resumes", required=True, help="Path to folder containing resumes")
    parser_args.add_argument("--out", default="results.json", help="Path to write full JSON results")
    args = parser_args.parse_args()

    run(args.jd, args.resumes, args.out)