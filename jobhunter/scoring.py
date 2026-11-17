"""Rule-based 0-100 scoring from keywords.yaml (no AI model).

How a score is built:
  1. Each positive keyword GROUP (automation, ai, video, arabic, fit) adds the weights of its matched
     rules (a match in the title counts `title_multiplier`x), then is CAPPED at the group's `cap`,
     so one area (e.g. five video tools) can't max out the score on its own.
  2. A one-time `title_bonus` is added when a strong rule (weight >= title_bonus_min_weight) is in
     the title — the job is *about* the skill, not just mentioning it.
  3. The positive total is normalised with a saturating curve: 100 * (1 - exp(-raw / scale)).
     Reaching 80+ needs raw >= ~1.6 x scale, i.e. strong matches across several groups.
  4. Penalty GROUPS (seniority, language, tools_required, location, other) subtract flat points,
     each group capped too. Some penalties are detectors (non-English posting, tools listed as
     REQUIRED, region lists that leave out Iraq) rather than plain keywords.
  5. Final score = clamp(normalised - penalties, 0, 100).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .eligibility import region_list_excluding_iraq

# --------------------------------------------------------------------------- rules


@dataclass
class Rule:
    label: str
    pattern: re.Pattern
    weight: float          # points when matched in the title (positive rules: x title_multiplier)
    desc_weight: float     # points when matched only in the description


def _compile(item: dict, title_multiplier: float = 1.0) -> Rule:
    flags = 0 if item.get("case_sensitive") else re.I
    if "regex" in item:
        pat = item["regex"]
        label = item.get("label") or item["regex"][:25]
    else:
        term = item["term"]
        plural = r"(?:s|es)?" if term[-1:].isalpha() else ""  # "ai agent" also matches "ai agents"
        pat = r"(?<![\w])" + re.escape(term).replace(r"\ ", r"[\s\-]+") + plural + r"(?![\w])"
        label = item.get("label") or term
    w = float(item["weight"])
    if item.get("title_only"):
        desc_w = 0.0
    else:
        desc_w = float(item.get("desc_weight", w))
    title_w = float(item.get("title_weight", w * title_multiplier if w > 0 else w))
    return Rule(label=label, pattern=re.compile(pat, flags), weight=title_w, desc_weight=desc_w)


@dataclass
class Group:
    name: str
    cap: float
    rules: list[Rule] = field(default_factory=list)


# --------------------------------------------------------------------------- detectors

_EN_STOPWORDS = set(
    "the and to of a in you for with is are our we will on as be your this that or an at by "
    "from have it can who what about all their they us has not more work team".split()
)


def non_english(text: str) -> bool:
    """True when the posting is clearly not written in English.
    Arabic-script postings are NOT penalised (Arabic is a target language)."""
    sample = (text or "")[:2500]
    letters = re.findall(r"[^\W\d_]", sample)
    if len(letters) < 80:
        return False
    arabic = sum(1 for c in letters if "؀" <= c <= "ۿ")
    latin = sum(1 for c in letters if c.isascii() or "À" <= c <= "ɏ")
    if arabic / len(letters) > 0.3:
        return False                      # Arabic posting: fine
    if latin / len(letters) < 0.5:
        return True                       # Cyrillic, CJK, etc.
    words = re.findall(r"[A-Za-zÀ-ɏ']+", sample.lower())
    if len(words) < 25:
        return False
    ratio = sum(1 for w in words if w in _EN_STOPWORDS) / len(words)
    return ratio < 0.12                   # English prose is typically 0.25-0.40


_REQ_HEADING = re.compile(
    r"^\W*(?:requirements?|qualifications?|must[\s\-]haves?|what\s+you(?:'ll|\s+will)?\s+need|"
    r"what\s+we(?:'re|\s+are)\s+looking\s+for|you\s+(?:have|bring|are)|skills\s+required|"
    r"required\s+skills|who\s+you\s+are|minimum\s+qualifications|basic\s+qualifications)\b",
    re.I,
)
_OPT_HEADING = re.compile(
    r"^\W*(?:nice[\s\-]to[\s\-]haves?|bonus(?:\s+points)?|preferred(?:\s+qualifications)?|"
    r"good[\s\-]to[\s\-]haves?|pluses|extra\s+credit|benefits|what\s+we\s+offer|perks|responsibilities|"
    r"what\s+you(?:'ll|\s+will)\s+do)\b",
    re.I,
)
_REQ_WORDS = re.compile(r"\b(?:required|requirement|must|mandatory|essential|proficien\w*|expert(?:ise)?\s+in|"
                        r"mastery|advanced|strong\s+(?:knowledge|experience|command)|\d+\+?\s*years)\b", re.I)
_OPT_WORDS = re.compile(r"nice[\s\-]to[\s\-]have|\bbonus\b|\bplus\b|preferred|a\s+plus|good\s+to\s+have|"
                        r"familiarity|is\s+an\s+advantage|optional", re.I)


def required_tools(text: str, tool_patterns: list[tuple[str, re.Pattern]]) -> list[str]:
    """Return labels of tools listed as REQUIRED: on a line inside a Requirements-type section,
    or on a line that itself says required/must/proficient — and not marked nice-to-have."""
    found: list[str] = []
    section = None
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        short = len(stripped) < 60
        if short and _REQ_HEADING.search(stripped):
            section = "req"
        elif short and _OPT_HEADING.search(stripped):
            section = "opt"
        for label, pat in tool_patterns:
            if label in found or not pat.search(stripped):
                continue
            if _OPT_WORDS.search(stripped):
                continue
            if section == "req" or _REQ_WORDS.search(stripped):
                found.append(label)
    return found


# --------------------------------------------------------------------------- scorer


class Scorer:
    def __init__(self, config: dict):
        sc = config.get("scoring", {})
        self.title_multiplier = float(sc.get("title_multiplier", 2.0))
        self.scale = float(sc.get("scale", 70))
        self.title_bonus = float(sc.get("title_bonus", 25))
        self.title_bonus_min_weight = float(sc.get("title_bonus_min_weight", 20))

        self.groups = [
            Group(name, float(g["cap"]), [_compile(r, self.title_multiplier) for r in g["rules"]])
            for name, g in (config.get("groups") or {}).items()
        ]
        self.penalties = [
            Group(name, float(g["cap"]), [_compile(r) for r in g.get("rules", [])])
            for name, g in (config.get("penalties") or {}).items()
        ]
        det = config.get("detectors") or {}
        self.det_non_english = det.get("non_english")                # {weight, group}
        self.det_region = det.get("region_list_excludes_iraq")      # {weight, group}
        self.det_tools = det.get("required_tools")                   # {weight, group, tools: [...]}
        self.tool_patterns = [
            (t, re.compile(r"(?<![\w])" + re.escape(t).replace(r"\ ", r"[\s\-]*") + r"(?![\w])", re.I))
            for t in (self.det_tools or {}).get("tools", [])
        ]

    # -- helpers
    @staticmethod
    def _match(rule: Rule, title: str, desc: str) -> tuple[float, bool]:
        if rule.pattern.search(title):
            return rule.weight, True
        if rule.desc_weight and rule.pattern.search(desc):
            return rule.desc_weight, False
        return 0.0, False

    def score(self, title: str, description: str) -> tuple[int, str, bool]:
        """Return (score 0-100, one-line reason, relevant?).
        relevant = at least one positive rule matched."""
        title = title or ""
        desc = description or ""

        # 1. positive groups, capped
        raw = 0.0
        pos_parts, strong_in_title = [], False
        for g in self.groups:
            pts, labels = 0.0, []
            for r in g.rules:
                p, in_title = self._match(r, title, desc)
                if p:
                    pts += p
                    labels.append(r.label + ("*" if in_title else ""))
                    if in_title and r.desc_weight >= self.title_bonus_min_weight:
                        strong_in_title = True
            if labels:
                capped = min(pts, g.cap)
                raw += capped
                pos_parts.append(f"{g.name} {capped:.0f}{'↑' if pts > g.cap else ''}: {', '.join(labels)}")
        relevant = bool(pos_parts)
        if strong_in_title:
            raw += self.title_bonus
            pos_parts.append(f"title +{self.title_bonus:.0f}")

        # 3. normalise
        base = 100.0 * (1.0 - math.exp(-raw / self.scale))

        # 4. penalties, capped per group
        pen_hits: dict[str, list[tuple[str, float]]] = {g.name: [] for g in self.penalties}
        caps = {g.name: g.cap for g in self.penalties}
        for g in self.penalties:
            for r in g.rules:
                p, in_title = self._match(r, title, desc)
                if p:
                    pen_hits[g.name].append((r.label + ("*" if in_title else ""), p))

        def add(det: dict | None, label: str):
            if det:
                grp = det.get("group", "other")
                pen_hits.setdefault(grp, []).append((label, float(det["weight"])))
                caps.setdefault(grp, float(det.get("cap", det["weight"])))

        if self.det_non_english and non_english(title + "\n" + desc):
            add(self.det_non_english, "non-English posting")
        if self.det_region:
            places = region_list_excluding_iraq(desc)
            if places:
                add(self.det_region, f"region list w/o Iraq ({places})")
        if self.det_tools and self.tool_patterns:
            for tool in required_tools(desc, self.tool_patterns):
                add(self.det_tools, f"{tool} required")

        penalty, neg_parts = 0.0, []
        for name, hits in pen_hits.items():
            if not hits:
                continue
            total = max(sum(p for _, p in hits), caps[name])   # caps are negative numbers
            penalty += total
            neg_parts.append(f"{name} {total:.0f}: {', '.join(l for l, _ in hits)}")

        score = max(0, min(100, round(base + penalty)))
        reason = " · ".join(pos_parts) if pos_parts else "no keyword matches"
        if neg_parts:
            reason += " | − " + " · ".join(neg_parts)
        return score, reason, relevant
