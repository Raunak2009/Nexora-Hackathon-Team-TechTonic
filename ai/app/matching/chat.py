"""Recruiter chat layer - answers questions about a ranking. No LLM, no API key.

The judges will ask how this works, so the design is deliberately simple and
inspectable: a question is routed to one of a small set of intents by pattern,
each intent is answered by reading the score trace the engine already computed,
and the reply is assembled from real values.

Supported intents
  compare        "why is Aarav ranked above Nikhil?"
  explain        "why is #3 ranked there?"  /  "tell me about Sanjana"
  who_has        "who knows Docker?"  /  "which candidates have AWS and React?"
  who_lacks      "who is missing MongoDB?"
  add_requirement "I want someone who has deployed to production"  (re-ranks)
  filter         "show me candidates with at least 2 years"
  best           "who should I interview?"  /  "top 3"
  gaps           "what is this pool missing?"
  flags          "anything suspicious?"
  confidence     "who is most convincing?"

Anything it cannot route, it says so and lists what it can answer - rather than
inventing a confident-sounding non-answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .explain import compare_candidates, explain_candidate
from .skills import get_ontology


@dataclass
class ChatReply:
    intent: str
    answer: str
    candidates: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    reranked: bool = False

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "answer": self.answer,
            "candidates": self.candidates,
            "data": self.data,
            "reranked": self.reranked,
        }


_COMPARE_RE = re.compile(
    r"\b(?:why\s+is|why\s+are|compare|difference\s+between|vs\.?|versus)\b", re.I)
_ABOVE_RE = re.compile(
    r"(.+?)\s+(?:ranked?\s+)?(?:above|over|higher\s+than|better\s+than|ahead\s+of|vs\.?|versus|and)\s+(.+?)[\?\.]?$",
    re.I)
_WHO_HAS_RE = re.compile(
    r"\b(?:who|which\s+candidates?|anyone|any\s+candidate)\b.*\b(?:has|have|knows?|"
    r"with|worked\s+with|used|experience\s+(?:in|with))\b", re.I)
_WHO_LACKS_RE = re.compile(
    r"\b(?:who|which\s+candidates?)\b.*\b(?:lacks?|missing|without|does\s*n[o']t\s+have|"
    r"do\s*n[o']t\s+have|no\s+experience)\b", re.I)
_EXPLAIN_RE = re.compile(
    r"\b(?:why|explain|tell\s+me\s+about|what\s+about|how\s+did|reason\s+for)\b", re.I)
_BEST_RE = re.compile(
    r"\b(?:who\s+should\s+i|best|top\s*\d*|shortlist|recommend|interview|pick|"
    r"strongest|front\s*runner)\b", re.I)
_GAPS_RE = re.compile(
    r"\b(?:gap|gaps|missing|nobody|no\s+one|weakest|scarce|hard\s+to\s+find|"
    r"pool\s+(?:is\s+)?(?:missing|lacking|weak))\b", re.I)
_FLAG_RE = re.compile(
    r"\b(?:flag|flagged|suspicious|suspect|fraud|fake|inflated|lying|"
    r"red\s+flag|concern|worried|trust)\b", re.I)
_CONFIDENCE_RE = re.compile(
    r"\b(?:confiden|convincing|credible|believable|evidence|substantiat|"
    r"backed\s+up|proof|real\s+work)\b", re.I)
_FILTER_RE = re.compile(
    r"\b(?:show\s+me|filter|only|at\s+least|more\s+than|less\s+than|minimum|"
    r"under|over|fresher|freshers?\s+only)\b", re.I)
_WANT_RE = re.compile(
    r"\b(?:i\s+(?:want|need|am\s+looking\s+for|'?d\s+like)|we\s+(?:want|need|are\s+looking\s+for)|"
    r"looking\s+for|must\s+(?:have|be)|should\s+(?:have|be|know)|prioriti[sz]e|"
    r"care\s+more\s+about|ideal\s+candidate|my\s+ideal)\b", re.I)
_YEARS_RE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)", re.I)


def _fmt_list(items: list[str], limit: int = 6) -> str:
    items = [i for i in items if i]
    if not items:
        return "none"
    shown = items[:limit]
    extra = len(items) - len(shown)
    body = shown[0] if len(shown) == 1 else ", ".join(shown[:-1]) + " and " + shown[-1]
    return body + (f" (+{extra} more)" if extra else "")


class RecruiterChat:
    """Wraps a ShortlistEngine and answers questions about its ranking."""

    def __init__(self, engine):
        self.engine = engine
        self.ontology = get_ontology()

    # -- helpers ------------------------------------------------------------
    def _find(self, text: str):
        return self.engine.find(text)

    def _skills_in(self, text: str) -> list[str]:
        return [h.key for h in self.ontology.extract(text, section="skills")]

    # -- entry point --------------------------------------------------------
    def ask(self, question: str) -> ChatReply:
        q = question.strip()
        if not q:
            return ChatReply("unknown", "Ask me something about this shortlist.")
        if not self.engine.candidates:
            self.engine.run()

        # Order matters: the most specific patterns are tried first.
        for handler in (
            self._try_compare,
            self._try_flags,
            self._try_confidence,
            self._try_gaps,
            self._try_requirements,
            self._try_who_lacks,
            self._try_who_has,
            self._try_filter,
            self._try_explain,
            self._try_best,
        ):
            reply = handler(q)
            if reply is not None:
                return reply

        return ChatReply(
            "unknown",
            "I couldn't map that to something I can answer from the ranking. "
            "I can handle: comparisons (\"why is X above Y\"), single-candidate "
            "explanations, \"who has <skill>\", \"who is missing <skill>\", "
            "\"I want someone who ...\" (re-ranks the pool), experience filters, "
            "pool-wide gaps, flagged candidates, and confidence.",
        )

    # -- intents ------------------------------------------------------------
    def _try_compare(self, q: str) -> ChatReply | None:
        if not _COMPARE_RE.search(q):
            return None
        m = _ABOVE_RE.search(q)
        if not m:
            return None
        a_txt = re.sub(r"^\s*why\s+is\s+", "", m.group(1), flags=re.I).strip(" ?.")
        b_txt = m.group(2).strip(" ?.")
        a, b = self._find(a_txt), self._find(b_txt)
        if a is None or b is None:
            return None
        return ChatReply(
            "compare",
            compare_candidates(a, b, self.engine.jd),
            candidates=[a.resume.name, b.resume.name],
            data={"a": a.to_dict(), "b": b.to_dict()},
        )

    def _try_explain(self, q: str) -> ChatReply | None:
        if not _EXPLAIN_RE.search(q):
            return None
        # Pull out whatever looks like a candidate reference.
        for token in re.findall(r"#?\d+|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?|[\w\-]+\.\w+", q):
            c = self._find(token.lstrip("#"))
            if c is not None:
                if not c.explanation:
                    c.explanation = explain_candidate(c, self.engine.jd)
                return ChatReply("explain", c.explanation,
                                 candidates=[c.resume.name], data={"candidate": c.to_dict()})
        return None

    def _try_who_has(self, q: str) -> ChatReply | None:
        if not _WHO_HAS_RE.search(q):
            return None
        keys = self._skills_in(q)
        if not keys:
            return None
        names = [self.ontology.canonical(k) for k in keys]

        rows = []
        for c in self.engine.candidates:
            matched = [k for k in keys if k in c.resume.skill_keys]
            if matched:
                rows.append((c, matched))

        if not rows:
            return ChatReply("who_has",
                             f"Nobody in this pool of {len(self.engine.candidates)} "
                             f"names {_fmt_list(names)}. That is worth knowing: the JD "
                             f"may be asking for something this applicant pool does not have.",
                             data={"skills": names, "matches": []})

        rows.sort(key=lambda kv: (-len(kv[1]), kv[0].rank))
        lines = [f"{len(rows)} of {len(self.engine.candidates)} candidates name "
                 f"{_fmt_list(names)}:"]
        for c, matched in rows[:8]:
            hit = c.resume.skill(matched[0])
            ev = f" - \"{hit.evidence[:70]}\"" if hit else ""
            lines.append(f"#{c.rank} {c.resume.name} ({c.score:.1f}): "
                         f"{_fmt_list([self.ontology.canonical(k) for k in matched])}{ev}")
        return ChatReply("who_has", " ".join(lines[:1]) + "\n" + "\n".join(lines[1:]),
                         candidates=[c.resume.name for c, _ in rows],
                         data={"skills": names,
                               "matches": [{"rank": c.rank, "candidate": c.resume.name,
                                            "score": c.score,
                                            "skills": [self.ontology.canonical(k) for k in mm]}
                                           for c, mm in rows]})

    def _try_who_lacks(self, q: str) -> ChatReply | None:
        if not _WHO_LACKS_RE.search(q):
            return None
        keys = self._skills_in(q)
        if not keys:
            return None
        names = [self.ontology.canonical(k) for k in keys]
        rows = [c for c in self.engine.candidates
                if not set(keys) <= c.resume.skill_keys]
        if not rows:
            return ChatReply("who_lacks",
                             f"Every candidate in the pool names {_fmt_list(names)}.",
                             data={"skills": names})
        listing = "\n".join(f"#{c.rank} {c.resume.name} ({c.score:.1f})" for c in rows[:10])
        return ChatReply("who_lacks",
                         f"{len(rows)} of {len(self.engine.candidates)} candidates do not "
                         f"name {_fmt_list(names)}:\n{listing}",
                         candidates=[c.resume.name for c in rows],
                         data={"skills": names})

    def _try_requirements(self, q: str) -> ChatReply | None:
        """'I want someone who ...' - treat the sentence as extra requirements
        and re-rank the pool against JD + that sentence."""
        if not _WANT_RE.search(q):
            return None
        # "who has Docker?" is a lookup, not a new requirement - even though
        # "must have" style wording can appear inside it.
        if re.match(r"\s*(?:who|which|what|is|are|does|do|can)\b", q, re.I):
            return None

        result = self.engine.rerank_with_extra_requirements(q)
        if result is None:
            return None

        named = [self.ontology.canonical(k) for k in self._skills_in(q)]
        top = result["ranking"][:5]
        moves = result["movements"][:5]

        parts = [f"Re-ranked all {len(self.engine.candidates)} candidates with your "
                 f"extra requirement weighted alongside the JD."]
        if named:
            parts.append(f"I picked out {_fmt_list(named)} as concrete skills in what "
                         f"you wrote; the rest was matched on meaning.")
        else:
            parts.append("No specific technology was named, so this was matched purely "
                         "on meaning against each resume's bullets.")
        parts.append("New top 3: " + ", ".join(
            f"{i+1}. {c['candidate']} ({c['score']:.1f})" for i, c in enumerate(top[:3])) + ".")
        if moves:
            parts.append("Biggest movers: " + "; ".join(
                f"{m['candidate']} {m['from']}->{m['to']}" for m in moves) + ".")

        return ChatReply("add_requirement", " ".join(parts),
                         candidates=[c["candidate"] for c in top],
                         data=result, reranked=True)

    def _try_filter(self, q: str) -> ChatReply | None:
        if not _FILTER_RE.search(q):
            return None
        from ..reporting.matrix import Filters, apply_filters

        f = Filters()
        applied = False

        ym = _YEARS_RE.search(q)
        if ym:
            years = float(ym.group(1))
            if re.search(r"\b(?:under|less\s+than|below|at\s+most|no\s+more\s+than)\b", q, re.I):
                f.max_years = years
            else:
                f.min_years = years
            applied = True

        if re.search(r"\bfresher|student|no\s+experience\b", q, re.I):
            f.freshers_only = True
            applied = True

        keys = self._skills_in(q)
        if keys:
            f.must_have_skills = keys
            applied = True

        if not applied:
            return None

        kept = apply_filters(self.engine.candidates, f, self.ontology)
        if not kept:
            return ChatReply("filter",
                             f"No candidate matches {_fmt_list(f.describe())}.",
                             data={"filters": f.describe(), "results": []})
        listing = "\n".join(
            f"#{c.rank} {c.resume.name} ({c.score:.1f}, {c.resume.years_experience:.1f} yrs)"
            for c in kept[:10])
        return ChatReply("filter",
                         f"{len(kept)} of {len(self.engine.candidates)} match "
                         f"{_fmt_list(f.describe())}. Ranks are their position in the "
                         f"full pool, not within the filter:\n{listing}",
                         candidates=[c.resume.name for c in kept],
                         data={"filters": f.describe(),
                               "results": [c.to_dict() for c in kept]})

    def _try_best(self, q: str) -> ChatReply | None:
        if not _BEST_RE.search(q):
            return None
        n = 3
        nm = re.search(r"top\s*(\d{1,2})", q, re.I)
        if nm:
            n = max(1, min(int(nm.group(1)), len(self.engine.candidates)))
        top = self.engine.candidates[:n]
        for c in top:
            if not c.explanation:
                c.explanation = explain_candidate(c, self.engine.jd)
        body = "\n\n".join(c.explanation for c in top)
        return ChatReply("best", f"Top {n} for {self.engine.jd.title}:\n\n{body}",
                         candidates=[c.resume.name for c in top],
                         data={"top": [c.to_dict() for c in top]})

    def _try_gaps(self, q: str) -> ChatReply | None:
        if not _GAPS_RE.search(q):
            return None
        jd = self.engine.jd
        total = len(self.engine.candidates) or 1
        rows = []
        for hit in jd.required_skills:
            have = sum(1 for c in self.engine.candidates
                       if any(m.key == hit.key and m.status == "exact" for m in c.required_matches))
            rows.append((hit.canonical, have, round(100 * have / total, 1)))
        rows.sort(key=lambda r: r[1])

        scarce = [r for r in rows if r[2] < 25]
        lines = [f"Pool coverage of the {len(rows)} required skills, weakest first:"]
        lines += [f"  {name}: {have}/{total} candidates ({pct}%)" for name, have, pct in rows[:8]]
        if scarce:
            lines.append(f"\n{_fmt_list([s[0] for s in scarce])} are close to absent from "
                         f"this pool. If the role genuinely needs them you are hiring "
                         f"against the market; if not, they belong in 'nice to have'.")
        return ChatReply("gaps", "\n".join(lines),
                         data={"coverage": [{"skill": n, "have": h, "pct": p} for n, h, p in rows]})

    def _try_flags(self, q: str) -> ChatReply | None:
        if not _FLAG_RE.search(q):
            return None
        flagged = [c for c in self.engine.candidates if c.integrity_flags]
        if not flagged:
            return ChatReply("flags", "No integrity flags raised on any candidate in "
                                      "this pool.", data={"flagged": []})
        lines = [f"{len(flagged)} of {len(self.engine.candidates)} candidates raised flags:"]
        for c in flagged[:10]:
            for f in c.integrity_flags[:2]:
                lines.append(f"  #{c.rank} {c.resume.name} [{f.severity.upper()}] {f.title}"
                             + (f" - {f.evidence[:70]}" if f.evidence else ""))
        return ChatReply("flags", "\n".join(lines),
                         candidates=[c.resume.name for c in flagged],
                         data={"flagged": [
                             {"rank": c.rank, "candidate": c.resume.name,
                              "flags": [f.to_dict() for f in c.integrity_flags]}
                             for c in flagged]})

    def _try_confidence(self, q: str) -> ChatReply | None:
        if not _CONFIDENCE_RE.search(q):
            return None
        ranked = sorted((c for c in self.engine.candidates if c.confidence),
                        key=lambda c: -c.confidence.score)
        if not ranked:
            return None
        lines = ["Evidence confidence - how well each candidate BACKS UP what they "
                 "claim. This is separate from how well they match the JD:"]
        for c in ranked[:8]:
            lines.append(f"  {c.confidence.score:.0f} ({c.confidence.band}) - "
                         f"#{c.rank} {c.resume.name}: {c.confidence.reasons[0] if c.confidence.reasons else ''}")

        mismatch = [c for c in self.engine.candidates[:5]
                    if c.confidence and c.confidence.score < 40]
        if mismatch:
            lines.append(f"\nWorth a closer look: {_fmt_list([c.resume.name for c in mismatch])} "
                         f"rank well but their resumes are thin on evidence - strong "
                         f"keyword match, little described work.")
        return ChatReply("confidence", "\n".join(lines),
                         candidates=[c.resume.name for c in ranked],
                         data={"confidence": [
                             {"rank": c.rank, "candidate": c.resume.name,
                              **c.confidence.to_dict()} for c in ranked]})
