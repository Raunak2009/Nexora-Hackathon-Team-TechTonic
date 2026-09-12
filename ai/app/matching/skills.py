"""Skill ontology: alias-aware, typo-tolerant, relation-aware skill detection.

This is the *keyword* half of the hybrid, upgraded from naive substring search:

  1. Every skill has a canonical name plus surface aliases, so "reactjs",
     "React.js" and "React Hooks" all resolve to the same node.
  2. Skills have `related` edges, so a JD asking for React can give partial
     credit to a candidate who only lists Next.js - explicitly, with a
     different (lower) weight, and with the reason recorded.
  3. Matching is typo tolerant, because real resumes say "Javascrpit".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

from ..config import FUZZY_THRESHOLD, RESOURCES_DIR

# Short surface forms that would produce nonsense matches without guards.
_RISKY_SHORT = {"c", "r", "go", "ts", "js", "py", "ml", "os", "qa", "sh"}

# Fuzzy matching only fires on tokens this long or longer, and only when the
# edit distance is genuinely typo-sized. Both guards exist because a loose
# fuzzy pass silently invents skills, which is worse than missing one.
_FUZZY_MIN_LEN = 6
_FUZZY_MAX_EDITS = 2
# Common resume English that is close enough to a skill name to trip fuzzy
# matching. Cheaper and far more predictable than raising the threshold.
_FUZZY_STOPWORDS = {
    "about", "above", "acting", "action", "active", "against", "aware", "based",
    "basic", "basics", "below", "between", "class", "classes", "client", "clients",
    "company", "course", "courses", "create", "created", "design", "designed",
    "detail", "details", "during", "email", "every", "field", "first", "focus",
    "grade", "great", "group", "hobby", "hobbies", "include", "index", "issue",
    "issues", "later", "learn", "learning", "level", "major", "manage", "march",
    "minor", "mobile", "month", "months", "notes", "other", "others", "output",
    "phase", "place", "point", "points", "power", "present", "process", "product",
    "profile", "project", "projects", "quality", "queries", "query", "report",
    "reports", "result", "results", "review", "reviews", "score", "scored",
    "section", "senior", "server", "service", "services", "sheet", "sheets",
    "skill", "skills", "small", "solve", "solved", "source", "stage", "start",
    "state", "story", "strong", "study", "system", "systems", "table", "tables",
    "their", "there", "these", "third", "those", "times", "title", "total",
    "train", "under", "value", "values", "where", "which", "while", "white",
    "whole", "world", "would", "write", "writing", "written", "years",
    "code", "coding", "codes", "across", "around", "become", "before", "behind",
    "better", "change", "choose", "common", "course", "custom", "decide",
    "deploy", "detail", "domain", "driven", "enable", "ensure", "expect",
    "follow", "handle", "impact", "inside", "listed", "manage", "market",
    "matter", "medium", "member", "method", "mobile", "moving", "native",
    "number", "object", "office", "online", "option", "others", "output",
    "people", "period", "person", "policy", "public", "reason", "record",
    "reduce", "region", "remote", "return", "review", "sample", "scale",
    "school", "search", "second", "series", "should", "simple", "single",
    "social", "source", "status", "strong", "studio", "submit", "summer",
    "system", "target", "things", "though", "toward", "travel", "trends",
    "update", "usage", "useful", "various", "vision", "within", "worked",
}

_RISKY_PREFIX_BLOCKLIST = {
    "grade", "section", "class", "option", "batch", "division", "category",
    "plan", "type", "level", "rank", "part", "unit", "block", "group",
}


@dataclass
class SkillNode:
    key: str
    canonical: str
    category: str
    aliases: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    # How much this skill counts toward coverage. Soft skills ("teamwork")
    # appear on every resume and discriminate nothing, so they count less than
    # a hard technology the role actually runs on.
    importance: float = 1.0

    @property
    def surface_forms(self) -> list[str]:
        return [self.key] + list(self.aliases)


@dataclass
class SkillHit:
    key: str
    canonical: str
    surface: str          # the exact string found in the document
    evidence: str         # the line it was found in
    section: str = "other"
    exact: bool = True    # False when matched fuzzily (typo)


class SkillOntology:
    def __init__(self, nodes: dict[str, SkillNode]):
        self.nodes = nodes
        self._surface_to_key: dict[str, str] = {}
        for key, node in nodes.items():
            for form in node.surface_forms:
                self._surface_to_key.setdefault(form.lower(), key)

        # One big alternation, longest-first so "spring boot" beats "spring"
        # and "react native" beats "react".
        forms = sorted(self._surface_to_key, key=len, reverse=True)
        escaped = [re.escape(f).replace(r"\ ", r"[\s\-_]+") for f in forms]
        self._pattern = re.compile(
            r"(?<![A-Za-z0-9_])(" + "|".join(escaped) + r")(?![A-Za-z0-9_])",
            re.IGNORECASE,
        )
        self._vocab = list(self._surface_to_key.keys())

    # -- construction -------------------------------------------------------
    @classmethod
    def load(cls, path=None) -> "SkillOntology":
        path = path or (RESOURCES_DIR / "skills.json")
        raw = json.loads(open(path, encoding="utf-8").read())
        nodes = {
            key: SkillNode(
                key=key,
                canonical=val.get("canonical", key.title()),
                category=val.get("category", "other"),
                aliases=val.get("aliases", []),
                related=val.get("related", []),
                importance=float(val.get("importance", 1.0)),
            )
            for key, val in raw.items()
        }
        return cls(nodes)

    # -- lookup -------------------------------------------------------------
    def get(self, key: str) -> SkillNode | None:
        return self.nodes.get(key.lower())

    def canonical(self, key: str) -> str:
        node = self.get(key)
        return node.canonical if node else key

    def resolve(self, phrase: str) -> str | None:
        """Map an arbitrary phrase onto a skill key, if it names one."""
        p = re.sub(r"\s+", " ", phrase.strip().lower())
        if p in self._surface_to_key:
            return self._surface_to_key[p]
        m = self._pattern.search(p)
        if m:
            return self._surface_to_key[self._normalize_surface(m.group(1))]
        return self._fuzzy_resolve(p)

    def related_keys(self, key: str) -> set[str]:
        """Related skills, following ontology edges in both directions."""
        node = self.get(key)
        if not node:
            return set()
        out = {r.lower() for r in node.related if r.lower() in self.nodes}
        for other_key, other in self.nodes.items():
            if key in [r.lower() for r in other.related]:
                out.add(other_key)
        return out - {key}

    # -- extraction ---------------------------------------------------------
    def _normalize_surface(self, surface: str) -> str:
        s = re.sub(r"[\s\-_]+", " ", surface.strip().lower())
        if s in self._surface_to_key:
            return s
        for sep in ("", "."):
            alt = s.replace(" ", sep)
            if alt in self._surface_to_key:
                return alt
        return s

    def _fuzzy_resolve(self, token: str) -> str | None:
        if len(token) < 5:
            return None
        try:
            from rapidfuzz import process, fuzz  # type: ignore
        except ImportError:
            return None
        match = process.extractOne(token, self._vocab, scorer=fuzz.ratio,
                                   score_cutoff=FUZZY_THRESHOLD)
        return self._surface_to_key[match[0]] if match else None

    def extract(self, text: str, section: str = "other", fuzzy: bool = True) -> list[SkillHit]:
        """Find every ontology skill named in a block of text.

        Two passes: an exact alias pass, then a bounded fuzzy pass over the
        tokens the first pass did not consume. Real resumes contain
        "Javascrpit", "Mongo DB", "reactjs" and "Kubernets", and a system that
        only does exact matching quietly scores those candidates as if the skill
        were absent.
        """
        hits: dict[str, SkillHit] = {}

        for line in text.splitlines():
            if not line.strip():
                continue
            consumed: list[tuple[int, int]] = []
            for m in self._pattern.finditer(line):
                surface = m.group(1)
                norm = self._normalize_surface(surface)
                key = self._surface_to_key.get(norm)
                if key is None:
                    continue
                if not self._passes_guard(key, surface, line, m.start()):
                    continue
                consumed.append((m.start(), m.end()))
                if key not in hits:
                    hits[key] = SkillHit(
                        key=key, canonical=self.nodes[key].canonical, surface=surface,
                        evidence=line.strip()[:220], section=section,
                    )

            if fuzzy:
                for key, surface in self._fuzzy_tokens(line, consumed):
                    if key not in hits:
                        hits[key] = SkillHit(
                            key=key, canonical=self.nodes[key].canonical, surface=surface,
                            evidence=line.strip()[:220], section=section, exact=False,
                        )

        return list(hits.values())

    def _fuzzy_tokens(self, line: str, consumed: list[tuple[int, int]]):
        """Typo-tolerant second pass over tokens the exact pass did not match."""
        try:
            from rapidfuzz import fuzz, process  # type: ignore
            from rapidfuzz.distance import Levenshtein  # type: ignore
        except ImportError:
            return

        for m in re.finditer(r"[A-Za-z][A-Za-z0-9+#.]{4,19}", line):
            if any(s <= m.start() < e or s < m.end() <= e for s, e in consumed):
                continue
            token = m.group(0).lower().strip(".")
            # Length is checked AFTER stripping punctuation: "code." survived the
            # regex as 5 characters and then fuzzy-matched "xcode", tagging every
            # JD that says "review each other's code" as an iOS role.
            if len(token) < _FUZZY_MIN_LEN:
                continue
            if token in self._surface_to_key or token in _FUZZY_STOPWORDS:
                continue
            candidates = [v for v in self._vocab
                          if len(v) >= _FUZZY_MIN_LEN and abs(len(v) - len(token)) <= 2]
            if not candidates:
                continue
            match = process.extractOne(token, candidates, scorer=fuzz.ratio,
                                       score_cutoff=FUZZY_THRESHOLD)
            if not match:
                continue
            # Ratio alone is too generous on short strings. Require a real edit
            # distance of at most 2 as well - that is a typo, not a coincidence.
            if Levenshtein.distance(token, match[0]) > _FUZZY_MAX_EDITS:
                continue
            yield self._surface_to_key[match[0]], m.group(0)

    def _passes_guard(self, key: str, surface: str, line: str, pos: int) -> bool:
        """Reject obvious false positives for dangerously short skill names."""
        if surface.lower() not in _RISKY_SHORT:
            return True
        before = line[max(0, pos - 30):pos].lower()
        prev_words = re.findall(r"[a-z]+", before)
        if prev_words and prev_words[-1] in _RISKY_PREFIX_BLOCKLIST:
            return False
        # "C" on its own line, in a comma list, or next to a sibling language.
        context = line.lower()
        if any(sib in context for sib in
               ("program", "language", "c++", "java", "python", "skill",
                "technolog", "proficien", "coding", "develop")):
            return True
        return bool(re.search(r"[,/|]\s*" + re.escape(surface) + r"\s*[,/|]", line, re.I))

    def extract_with_sections(self, sections) -> list[SkillHit]:
        """Extract across detected sections, keeping the richest evidence line."""
        from ..parsing.sections import EVIDENCE_WEIGHT

        best: dict[str, SkillHit] = {}
        for sec in sections:
            for hit in self.extract(sec.text, section=sec.name):
                prev = best.get(hit.key)
                if prev is None or EVIDENCE_WEIGHT.get(hit.section, 0.7) > EVIDENCE_WEIGHT.get(prev.section, 0.7):
                    best[hit.key] = hit
        return list(best.values())


@lru_cache(maxsize=1)
def get_ontology() -> SkillOntology:
    return SkillOntology.load()
