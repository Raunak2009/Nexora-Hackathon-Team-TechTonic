#!/usr/bin/env python3
"""Command-line demo for the Smart Shortlisting Engine.

    python cli.py rank   --jd data/jd/Sample_JD.pdf --resumes data/resumes
    python cli.py rank   --jd data/jd/Sample_JD.pdf --resumes data/resumes --json out.json
    python cli.py why    --jd ... --resumes ... --candidate "Priya"
    python cli.py compare --jd ... --resumes ... --a 1 --b 4
    python cli.py audit  --jd data/jd/Sample_JD.pdf
    python cli.py parse  --file data/resumes/some_resume.pdf
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import WEIGHTS  # noqa: E402
from app.matching.bias import audit_jd  # noqa: E402
from app.parsing.jd import parse_jd  # noqa: E402
from app.parsing.resume import parse_resume  # noqa: E402
from app.pipeline import ShortlistEngine  # noqa: E402

BAR = "█"


def _bar(value: float, width: int = 18) -> str:
    filled = int(round(max(0.0, min(1.0, value)) * width))
    return BAR * filled + "·" * (width - filled)


def _print_ranking(engine: ShortlistEngine, top_explain: int) -> None:
    jd = engine.jd
    print()
    print("=" * 92)
    print(f"JOB: {jd.title}")
    print(f"     seniority={jd.seniority}  min_years={jd.min_years:g}  "
          f"pool={len(engine.resumes)} resumes")
    print(f"     required : {', '.join(s.canonical for s in jd.required_skills) or '(none detected)'}")
    print(f"     preferred: {', '.join(s.canonical for s in jd.preferred_skills) or '(none)'}")
    print(f"     encoder  : {engine.encoder_name}")
    for note in engine.encoder_notes:
        print(f"       ! {note}")
    print("=" * 92)
    print()
    print(f"{'#':>3}  {'CANDIDATE':<24} {'SCORE':>6} {'KEYWD':>6} {'SEM':>5} "
          f"{'CONF':>5} {'FLAG':>5}   REQUIRED SKILLS MET")
    print("-" * 92)

    for c in engine.candidates:
        met = sum(1 for m in c.required_matches if m.status != "missing")
        total = len(c.required_matches)
        conf = f"{c.confidence.score:>5.0f}" if c.confidence else "    -"
        flag = {"high": " HIGH", "medium": "  MED", "low": "  low"}.get(c.worst_flag, "    -")
        print(f"{c.rank:>3}  {c.resume.name[:24]:<24} {c.score:>6.1f} "
              f"{c.keyword_score * 100:>6.0f} {c.semantic_score * 100:>5.0f} "
              f"{conf} {flag}   {met}/{total} "
              f"{_bar(met / total if total else 0, 12)}")

    print()
    print("=" * 92)
    print(f"TOP {top_explain} - WHY THEY RANK HERE")
    print("=" * 92)
    for c in engine.candidates[:top_explain]:
        print()
        print(c.explanation)
        matched = [m for m in c.required_matches if m.status != "missing"]
        if matched:
            print("  evidence:")
            for m in matched[:6]:
                print(f"    [{m.status:<8}] {m.canonical:<22} <- \"{m.evidence[:70]}\"")
        if c.missing_required:
            print(f"  gaps: {', '.join(m.canonical for m in c.missing_required)}")
    print()


def _load_engine(args) -> ShortlistEngine:
    resume_path = Path(args.resumes)
    if resume_path.is_dir():
        engine = ShortlistEngine.from_folder(args.jd, resume_path)
    else:
        engine = ShortlistEngine.from_paths(args.jd, [resume_path])
    engine.run(explain_top=max(args.top, 3))
    return engine


def cmd_rank(args) -> int:
    engine = _load_engine(args)
    _print_ranking(engine, args.top)
    if args.json:
        payload = engine.result(explain_top=args.top, verbose=args.verbose)
        Path(args.json).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"JSON written to {args.json}")
    return 0


def cmd_why(args) -> int:
    engine = _load_engine(args)
    print()
    print(engine.why_ranked(args.candidate))
    print()
    return 0


def cmd_compare(args) -> int:
    engine = _load_engine(args)
    print()
    print(engine.why_above(args.a, args.b))
    print()
    return 0


def cmd_audit(args) -> int:
    jd = parse_jd(args.jd)
    report = audit_jd(jd)
    print()
    print(f"JD BIAS / NARROWNESS AUDIT - {jd.title}")
    print("-" * 78)
    print(report["summary"])
    print()
    for f in report["flags"]:
        print(f"  [{f['severity'].upper():<6}] {f['category']}: \"{f['phrase']}\"")
        print(f"           context : {f['context']}")
        print(f"           why     : {f['why']}")
        print(f"           suggest : {f['suggestion']}")
        print()
    if not report["flags"]:
        print("  (clean)")
    return 0


def cmd_matrix(args) -> int:
    engine = _load_engine(args)
    m = engine.matrix(include_preferred=False)
    cols = m["columns"]
    print()
    print("SKILL MATRIX  (Y = named, ~ = adjacent/implied, . = no evidence)")
    print()
    width = max(len(r["candidate"]) for r in m["rows"]) + 2
    header = " " * (width + 5) + " ".join(f"{c['label'][:7]:<8}" for c in cols)
    print(header)
    sym = {"exact": "Y", "related": "~", "semantic": "~", "missing": "."}
    for row in m["rows"]:
        cells = {c["key"]: c for c in row["cells"]}
        line = "".join(f"{sym[cells[c['key']]['status']]:<8} " for c in cols)
        print(f"{row['rank']:>3}  {row['candidate'][:width]:<{width}} {line}")
    print()
    print("Scarcest required skills in this pool: " + ", ".join(
        f"{c['skill']} ({c['pool_coverage_pct']:.0f}%)"
        for c in m["pool_coverage"] if c["kind"] == "required")[:200])
    return 0


def cmd_flags(args) -> int:
    engine = _load_engine(args)
    flagged = engine.flagged()
    print()
    if not flagged:
        print("No integrity flags raised.")
        return 0
    print(f"INTEGRITY FLAGS - {len(flagged)} of {len(engine.candidates)} candidates")
    print("-" * 78)
    for c in flagged:
        print(f"\n#{c['rank']} {c['candidate']}  ({c['file']})")
        for f in c["flags"]:
            print(f"  [{f['severity'].upper():<6}] {f['title']}")
            print(f"           {f['detail']}")
            if f["evidence"]:
                print(f"           evidence: {f['evidence'][:100]}")
    return 0


def cmd_chat(args) -> int:
    engine = _load_engine(args)
    if args.message:
        print()
        print(engine.chat(args.message)["answer"])
        print()
        return 0
    print("\nRecruiter chat. Ask about the shortlist; blank line or 'quit' to exit.")
    print("Try: 'why is #1 above #3', 'who knows Docker', 'I want someone who has "
          "shipped to production', 'anything suspicious', 'what is this pool missing'\n")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in {"quit", "exit"}:
            break
        reply = engine.chat(q)
        print(f"\n[{reply['intent']}] {reply['answer']}\n")
    return 0


def cmd_report(args) -> int:
    from app.reporting.pdf import REPORTS

    engine = _load_engine(args)
    out_dir = Path(args.out or ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    kinds = [args.kind] if args.kind != "all" else list(REPORTS)
    for kind in kinds:
        fn = REPORTS[kind]
        pdf = fn(engine, args.top) if kind == "top_explanations" else fn(engine)
        path = out_dir / f"{kind}.pdf"
        path.write_bytes(pdf)
        print(f"  wrote {path}  ({len(pdf):,} bytes)")
    return 0


def cmd_parse(args) -> int:
    r = parse_resume(args.file)
    print(json.dumps(r.to_dict(), indent=2, default=str))
    print("\n--- first 15 chunks ---")
    for ch in r.chunks[:15]:
        print(f"  [{ch.section:<14}] {ch.text[:90]}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="cli.py", description="Smart Shortlisting Engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--jd", required=True, help="Path to the job description file")
        sp.add_argument("--resumes", required=True, help="Folder (or single file) of resumes")

    sp = sub.add_parser("rank", help="Rank the whole pool against the JD")
    add_common(sp)
    sp.add_argument("--top", type=int, default=3, help="How many to explain (default 3)")
    sp.add_argument("--json", help="Also write the full result as JSON here")
    sp.add_argument("--verbose", action="store_true", help="Include full evidence in JSON")
    sp.set_defaults(func=cmd_rank)

    sp = sub.add_parser("why", help="Explain one candidate's ranking")
    add_common(sp)
    sp.add_argument("--candidate", required=True, help="Name, filename or rank number")
    sp.add_argument("--top", type=int, default=3)
    sp.set_defaults(func=cmd_why)

    sp = sub.add_parser("compare", help="Why is A ranked above B?")
    add_common(sp)
    sp.add_argument("--a", required=True)
    sp.add_argument("--b", required=True)
    sp.add_argument("--top", type=int, default=3)
    sp.set_defaults(func=cmd_compare)

    sp = sub.add_parser("matrix", help="Candidate x skill grid in the terminal")
    add_common(sp)
    sp.add_argument("--top", type=int, default=3)
    sp.set_defaults(func=cmd_matrix)

    sp = sub.add_parser("flags", help="Integrity flags raised across the pool")
    add_common(sp)
    sp.add_argument("--top", type=int, default=3)
    sp.set_defaults(func=cmd_flags)

    sp = sub.add_parser("chat", help="Recruiter chat (interactive, or --message)")
    add_common(sp)
    sp.add_argument("--message", help="Ask one question and exit")
    sp.add_argument("--top", type=int, default=3)
    sp.set_defaults(func=cmd_chat)

    sp = sub.add_parser("report", help="Write the PDF reports")
    add_common(sp)
    sp.add_argument("--kind", default="all",
                    choices=["all", "ranked_list", "top_explanations", "skill_gap"])
    sp.add_argument("--out", default="reports", help="Output directory")
    sp.add_argument("--top", type=int, default=3)
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("audit", help="Flag bias / over-narrow phrasing in the JD")
    sp.add_argument("--jd", required=True)
    sp.set_defaults(func=cmd_audit)

    sp = sub.add_parser("parse", help="Debug: show what we extracted from one file")
    sp.add_argument("--file", required=True)
    sp.set_defaults(func=cmd_parse)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
