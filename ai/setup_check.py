#!/usr/bin/env python3
"""Run this ONCE before the hackathon, on the laptop that will do the demo.

It checks every dependency and, crucially, pre-downloads the embedding model so
that on demo day the engine never needs network access. Venue wifi is the single
most likely thing to break a live demo.

    python setup_check.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

OK, WARN, FAIL = "  OK  ", " WARN ", " FAIL "
problems = 0
warnings = 0


def check(label: str, fn):
    global problems, warnings
    try:
        status, detail = fn()
    except Exception as exc:                      # noqa: BLE001
        status, detail = FAIL, f"{type(exc).__name__}: {exc}"
    if status == FAIL:
        problems += 1
    elif status == WARN:
        warnings += 1
    print(f"[{status}] {label:<34} {detail}")


def py_version():
    v = sys.version_info
    if v < (3, 9):
        return FAIL, f"Python {v.major}.{v.minor} - need 3.9+"
    return OK, f"Python {v.major}.{v.minor}.{v.micro}"


def mod(name: str, why: str, hard: bool = True):
    def inner():
        try:
            m = __import__(name)
            return OK, getattr(m, "__version__", "installed")
        except ImportError:
            return (FAIL if hard else WARN), f"missing - {why}"
    return inner


def embedding_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return WARN, "sentence-transformers not installed; LSA fallback will be used"

    from app.config import EMBEDDING_MODEL
    print(f"        downloading/loading {EMBEDDING_MODEL} (first run takes a minute)...")
    model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    vecs = model.encode(["built REST APIs with Express and MongoDB",
                         "developed backend services in Node.js"],
                        normalize_embeddings=True)
    sim = float(vecs[0] @ vecs[1])
    if sim < 0.4:
        return WARN, f"model loaded but synonym similarity is low ({sim:.2f})"
    return OK, f"cached and working (Express/MongoDB vs Node.js similarity {sim:.2f})"


def doc_tool():
    for tool in ("antiword", "catdoc", "soffice", "libreoffice"):
        if shutil.which(tool):
            return OK, f"{tool} found - legacy .doc files will read cleanly"
    return WARN, "no antiword/catdoc/libreoffice - legacy .doc falls back to salvage"


def end_to_end():
    from app.pipeline import ShortlistEngine

    root = Path(__file__).resolve().parent
    jd = root / "data" / "jd" / "Sample_JD.txt"
    pool = root / "data" / "validation"
    if not jd.exists() or not pool.exists():
        return WARN, "sample data missing - skipped"
    engine = ShortlistEngine.from_folder(jd, pool)
    engine.run()
    top = engine.candidates[0]
    spread = engine.candidates[0].score - engine.candidates[-1].score
    return OK, (f"ranked {len(engine.candidates)} resumes, top={top.resume.name} "
                f"({top.score:.1f}), spread={spread:.1f}, encoder={engine.encoder_name}")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    print("\nSmart Shortlisting Engine - environment check\n" + "-" * 70)
    check("Python version", py_version)
    check("numpy", mod("numpy", "required"))
    check("scikit-learn", mod("sklearn", "required for the LSA fallback"))
    check("rapidfuzz", mod("rapidfuzz", "typo tolerance will be disabled", hard=False))
    check("PyMuPDF (fitz)", mod("fitz", "PDF reading falls back to pdfplumber", hard=False))
    check("pdfplumber", mod("pdfplumber", "PDF fallback", hard=False))
    check("python-docx", mod("docx", ".docx resumes will not read", hard=False))
    check("fastapi", mod("fastapi", "API server will not start", hard=False))
    check("legacy .doc support", doc_tool)
    check("embedding model (pre-download)", embedding_model)
    check("end-to-end pipeline", end_to_end)
    print("-" * 70)
    if problems:
        print(f"\n{problems} blocking problem(s). Fix with: pip install -r requirements.txt\n")
        raise SystemExit(1)
    print(f"\nReady. {warnings} warning(s) - the engine will still run.\n")
