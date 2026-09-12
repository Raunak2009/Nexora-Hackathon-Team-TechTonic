"""Downloadable PDF reports, built with reportlab.

Three documents the recruiter can take away:
  ranked_list     - the full shortlist as a table
  top_explanations - why the top N ranked where they did, with evidence
  skill_gap       - the candidate x skill matrix plus what the pool is missing

Every figure is read off the ranking that already exists, so a PDF can never
disagree with the screen. Each report carries a footer stating the method and
the weights used, because a shortlist someone acts on should say how it was made.
"""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#6b6b6b")
RULE = colors.HexColor("#d9d9d9")
GREEN = colors.HexColor("#1a7f37")
AMBER = colors.HexColor("#9a6700")
RED = colors.HexColor("#b42318")
BAND = colors.HexColor("#f4f4f5")
HEAD_BG = colors.HexColor("#22272e")


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold",
                                fontSize=17, leading=21, textColor=INK, spaceAfter=2),
        "sub": ParagraphStyle("s", parent=ss["Normal"], fontName="Helvetica",
                              fontSize=9, leading=12, textColor=MUTED, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                             fontSize=12, leading=15, textColor=INK,
                             spaceBefore=12, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=ss["Heading3"], fontName="Helvetica-Bold",
                             fontSize=10, leading=13, textColor=INK,
                             spaceBefore=8, spaceAfter=3),
        "body": ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica",
                               fontSize=8.8, leading=12.5, textColor=INK,
                               alignment=TA_LEFT, spaceAfter=4),
        "small": ParagraphStyle("sm", parent=ss["Normal"], fontName="Helvetica",
                                fontSize=7.6, leading=10.5, textColor=MUTED),
        "quote": ParagraphStyle("q", parent=ss["Normal"], fontName="Helvetica-Oblique",
                                fontSize=8, leading=11, textColor=MUTED,
                                leftIndent=10, spaceAfter=2),
        "cell": ParagraphStyle("c", parent=ss["Normal"], fontName="Helvetica",
                               fontSize=7.6, leading=9.5, textColor=INK),
        "cellhead": ParagraphStyle("ch", parent=ss["Normal"], fontName="Helvetica-Bold",
                                   fontSize=7, leading=8.5, textColor=colors.white),
    }


def _esc(text) -> str:
    s = "" if text is None else str(text)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _footer(engine):
    sw = engine.simple_weights.as_dict()
    return (f"Generated {datetime.now():%d %b %Y %H:%M} &middot; "
            f"Smart Shortlisting Engine &middot; encoder: {_esc(engine.encoder_name)} "
            f"&middot; weights: keyword {sw['keyword']:.2f} / semantic {sw['semantic']:.2f} "
            f"/ experience {sw['experience']:.2f} &middot; "
            f"Scores are a decision aid, not a decision.")


def _header(story, st, title: str, engine, subtitle: str = ""):
    story.append(Paragraph(_esc(title), st["title"]))
    line = f"{_esc(engine.jd.title)} &middot; {len(engine.resumes)} candidates"
    if subtitle:
        line += f" &middot; {_esc(subtitle)}"
    story.append(Paragraph(line, st["sub"]))


def _build(story, landscape_mode: bool = False) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4) if landscape_mode else A4,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=13 * mm, bottomMargin=13 * mm,
        title="Smart Shortlisting Engine",
    )
    doc.build(story)
    return buf.getvalue()


def _flag_cell(candidate) -> tuple[str, colors.Color]:
    lvl = candidate.worst_flag
    if lvl == "high":
        return "HIGH", RED
    if lvl == "medium":
        return "MED", AMBER
    if lvl == "low":
        return "low", MUTED
    return "-", MUTED


# ---------------------------------------------------------------------------
# 1. Ranked list
# ---------------------------------------------------------------------------
def ranked_list_pdf(engine, candidates=None, filter_note: str = "") -> bytes:
    st = _styles()
    story = []
    rows_src = candidates if candidates is not None else engine.candidates

    _header(story, st, "Candidate Shortlist", engine, filter_note)

    head = ["#", "Candidate", "Score", "Skill", "Keyword", "Semantic",
            "Conf.", "Req. met", "Exp.", "Flag"]
    data = [head]
    for c in rows_src:
        met = sum(1 for m in c.required_matches if m.status == "exact")
        partial = sum(1 for m in c.required_matches if m.status in ("related", "semantic"))
        total = len(c.required_matches)
        flag_txt, _ = _flag_cell(c)
        data.append([
            str(c.rank),
            Paragraph(f"<b>{_esc(c.resume.name)}</b><br/>"
                      f"<font size=6.5 color='#6b6b6b'>{_esc(c.resume.path.name)}</font>",
                      st["cell"]),
            f"{c.score:.1f}",
            f"{c.subscores.required_skills * 100:.0f}",
            f"{c.keyword_score * 100:.0f}",
            f"{c.semantic_score * 100:.0f}",
            f"{c.confidence.score:.0f}" if c.confidence else "-",
            f"{met}/{total}" + (f" (+{partial})" if partial else ""),
            f"{c.resume.years_experience:.1f}y",
            flag_txt,
        ])

    tbl = Table(data, repeatRows=1, colWidths=[
        9 * mm, 52 * mm, 14 * mm, 13 * mm, 17 * mm, 18 * mm, 13 * mm, 20 * mm, 13 * mm, 13 * mm])

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i, c in enumerate(rows_src, start=1):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), BAND))
        if i <= 3:
            style.append(("FONTNAME", (2, i), (2, i), "Helvetica-Bold"))
            style.append(("TEXTCOLOR", (2, i), (2, i), GREEN))
        _, col = _flag_cell(c)
        style.append(("TEXTCOLOR", (9, i), (9, i), col))
    tbl.setStyle(TableStyle(style))
    story.append(tbl)

    story.append(Spacer(1, 7))
    story.append(Paragraph(
        "<b>Skill</b> = coverage of the JD's required skills. "
        "<b>Keyword</b> = skill coverage combined with BM25 term matching. "
        "<b>Semantic</b> = meaning-level match of resume bullets to JD requirements. "
        "<b>Conf.</b> = how well the resume evidences its own claims, independent of fit. "
        "<b>Req. met</b> = skills named outright, with partial/adjacent matches in brackets.",
        st["small"]))

    flagged = [c for c in rows_src if c.integrity_flags]
    if flagged:
        story.append(Paragraph("Flagged for human review", st["h2"]))
        for c in flagged:
            bullets = "<br/>".join(
                f"<b>[{f.severity.upper()}]</b> {_esc(f.title)} &mdash; {_esc(f.detail)}"
                for f in c.integrity_flags)
            story.append(Paragraph(f"<b>#{c.rank} {_esc(c.resume.name)}</b><br/>{bullets}",
                                   st["body"]))
            story.append(Spacer(1, 3))

    story.append(Spacer(1, 10))
    story.append(Paragraph(_footer(engine), st["small"]))
    return _build(story)


# ---------------------------------------------------------------------------
# 2. Top explanations
# ---------------------------------------------------------------------------
def top_explanations_pdf(engine, n: int = 3) -> bytes:
    from ..matching.explain import compare_candidates, explain_candidate

    st = _styles()
    story = []
    top = engine.candidates[:n]
    for c in top:
        if not c.explanation:
            c.explanation = explain_candidate(c, engine.jd)

    _header(story, st, f"Top {len(top)} Candidates - Reasoning", engine)

    for c in top:
        block = [Paragraph(f"#{c.rank} &nbsp; {_esc(c.resume.name)} "
                           f"&nbsp;&mdash;&nbsp; {c.score:.1f} / 100", st["h2"])]

        meta = Table([[
            f"Skill {c.subscores.required_skills * 100:.0f}",
            f"Keyword {c.keyword_score * 100:.0f}",
            f"Semantic {c.semantic_score * 100:.0f}",
            f"Experience {c.resume.years_experience:.1f}y",
            f"Confidence {c.confidence.score:.0f}" if c.confidence else "Confidence -",
        ]], colWidths=[36 * mm] * 5)
        meta.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BAND),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("BOX", (0, 0), (-1, -1), 0.4, RULE),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, RULE),
        ]))
        block.append(meta)
        block.append(Spacer(1, 6))
        block.append(Paragraph(_esc(c.explanation), st["body"]))
        story.append(KeepTogether(block))

        matched = [m for m in c.required_matches if m.status != "missing"]
        if matched:
            story.append(Paragraph("Evidence for each matched requirement", st["h3"]))
            rows = [["Skill", "How", "Line from the resume"]]
            for m in matched[:10]:
                rows.append([
                    Paragraph(f"<b>{_esc(m.canonical)}</b>", st["cell"]),
                    Paragraph(_esc(m.status), st["cell"]),
                    Paragraph(_esc(m.evidence[:150]) or "&mdash;", st["cell"]),
                ])
            t = Table(rows, repeatRows=1, colWidths=[32 * mm, 18 * mm, 132 * mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.4, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(t)

        if c.missing_required:
            story.append(Spacer(1, 5))
            story.append(Paragraph(
                "<b>Gaps:</b> " + _esc(", ".join(m.canonical for m in c.missing_required)),
                st["body"]))

        if c.confidence and c.confidence.reasons:
            story.append(Paragraph(
                f"<b>Confidence {c.confidence.score:.0f} ({_esc(c.confidence.band)}):</b> "
                + _esc("; ".join(c.confidence.reasons[:3])), st["small"]))

        if c.integrity_flags:
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                "<b>Flags:</b> " + _esc("; ".join(f"[{f.severity}] {f.title}"
                                                  for f in c.integrity_flags)), st["small"]))
        story.append(Spacer(1, 12))

    if len(top) > 1:
        story.append(PageBreak())
        story.append(Paragraph("How they differ", st["h2"]))
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                a, b = top[i], top[j]
                story.append(Paragraph(
                    f"<b>{_esc(a.resume.name)} vs {_esc(b.resume.name)}</b>", st["h3"]))
                story.append(Paragraph(_esc(compare_candidates(a, b, engine.jd)), st["body"]))
                story.append(Spacer(1, 4))

    story.append(Spacer(1, 8))
    story.append(Paragraph(_footer(engine), st["small"]))
    return _build(story)


# ---------------------------------------------------------------------------
# 3. Skill gap
# ---------------------------------------------------------------------------
def _tick_font() -> str:
    """A font that actually contains U+2713 / U+2717.

    Tries DejaVuSans (ships with matplotlib, and is installed system-wide on
    most Linux boxes), then a couple of common system paths. Falls back to
    ZapfDingbats, which is a core PDF font but renders as a box in a few
    viewers, and finally to plain letters - so the matrix is always legible.
    """
    global _TICK_FONT
    if _TICK_FONT is not None:
        return _TICK_FONT

    from pathlib import Path

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = []
    try:
        import matplotlib
        candidates.append(Path(matplotlib.__file__).parent
                          / "mpl-data" / "fonts" / "ttf" / "DejaVuSans.ttf")
    except Exception:
        pass
    candidates += [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    ]
    for path in candidates:
        try:
            if path.exists():
                pdfmetrics.registerFont(TTFont("TickFont", str(path)))
                _TICK_FONT = "TickFont"
                return _TICK_FONT
        except Exception:
            continue

    _TICK_FONT = "ZapfDingbats"
    return _TICK_FONT


_TICK_FONT = None
_ZAPF = {"exact": "4", "missing": "8"}
_UNICODE = {"exact": "\u2713", "missing": "\u2717"}
_COLOUR = {"exact": GREEN, "related": AMBER, "semantic": AMBER, "missing": RED}


def _cell_glyph(status: str) -> tuple[str, str]:
    """(text, fontname) for one matrix cell."""
    if status in ("related", "semantic"):
        return "\u2013", "Helvetica-Bold"          # en dash = partial credit
    font = _tick_font()
    if font == "ZapfDingbats":
        return _ZAPF[status], "ZapfDingbats"
    return _UNICODE[status], font


def skill_gap_pdf(engine, candidates=None, max_skills: int = 16) -> bytes:
    st = _styles()
    story = []
    rows_src = candidates if candidates is not None else engine.candidates
    matrix = engine.matrix()

    _header(story, st, "Skill Coverage and Gap Analysis", engine)

    columns = [c for c in matrix["columns"] if c["kind"] == "required"][:max_skills]
    keys = [c["key"] for c in columns]

    head = ["#", "Candidate"] + [
        Paragraph(_esc(c["label"]), st["cellhead"]) for c in columns]
    data = [head]

    by_doc = {r["doc_id"]: r for r in matrix["rows"]}
    style_cells = []
    for i, c in enumerate(rows_src, start=1):
        row_data = by_doc.get(c.resume.doc_id, {})
        cells = {x["key"]: x for x in row_data.get("cells", [])}
        row = [str(c.rank), Paragraph(_esc(c.resume.name), st["cell"])]
        for col_i, k in enumerate(keys, start=2):
            cell = cells.get(k, {"status": "missing"})
            status = cell["status"]
            glyph, font = _cell_glyph(status)
            row.append(glyph)
            style_cells.append(("TEXTCOLOR", (col_i, i), (col_i, i), _COLOUR[status]))
            style_cells.append(("FONTNAME", (col_i, i), (col_i, i), font))
        data.append(row)

    name_w = 40 * mm
    skill_w = max(9 * mm, (250 * mm - name_w) / max(1, len(keys)))
    tbl = Table(data, repeatRows=1, colWidths=[8 * mm, name_w] + [skill_w] * len(keys))
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
        ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (2, 0), (-1, -1), 2),
        ("RIGHTPADDING", (2, 0), (-1, -1), 2),
    ] + style_cells))
    story.append(tbl)

    story.append(Spacer(1, 5))
    yes_g, yes_f = _cell_glyph("exact")
    no_g, no_f = _cell_glyph("missing")
    story.append(Paragraph(
        f"<font face='{yes_f}' color='#1a7f37'>{yes_g}</font> named outright "
        f"&nbsp;&nbsp; <font color='#9a6700'><b>&ndash;</b></font> adjacent skill or "
        f"implied by context &nbsp;&nbsp; "
        f"<font face='{no_f}' color='#b42318'>{no_g}</font> no evidence", st["small"]))

    story.append(Paragraph("What this pool is short of", st["h2"]))
    cov = [c for c in matrix["pool_coverage"] if c["kind"] == "required"]
    rows = [["Required skill", "Candidates with it", "% of pool"]]
    for c in cov:
        rows.append([c["skill"], f"{c['candidates_with_skill']} / {len(rows_src)}",
                     f"{c['pool_coverage_pct']:.0f}%"])
    t = Table(rows, repeatRows=1, colWidths=[70 * mm, 45 * mm, 30 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    story.append(t)

    scarce = [c for c in cov if c["pool_coverage_pct"] < 25]
    if scarce:
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "<b>Read this as a signal about the JD, not only the candidates.</b> "
            + _esc(", ".join(c["skill"] for c in scarce))
            + " are close to absent from this applicant pool. If the role genuinely "
              "needs them, you are hiring against the market. If it does not, they "
              "belong in 'nice to have' where they will stop suppressing otherwise "
              "strong candidates.", st["body"]))

    audit = engine.result(include_bias=True).get("jd_bias_audit", {})
    if audit.get("flags"):
        story.append(Paragraph("Job description audit", st["h2"]))
        story.append(Paragraph(_esc(audit.get("summary", "")), st["body"]))
        for f in audit["flags"][:8]:
            story.append(Paragraph(
                f"<b>[{f['severity'].upper()}] {_esc(f['category'])}:</b> "
                f"\"{_esc(f['phrase'])}\" &mdash; {_esc(f['suggestion'])}", st["small"]))
            story.append(Spacer(1, 2))

    story.append(Spacer(1, 8))
    story.append(Paragraph(_footer(engine), st["small"]))
    return _build(story, landscape_mode=True)


# ---------------------------------------------------------------------------
REPORTS = {
    "ranked_list": ranked_list_pdf,
    "top_explanations": top_explanations_pdf,
    "skill_gap": skill_gap_pdf,
}
