"""Rule-based 0-100 scoring from keywords.yaml (no AI model)."""
from __future__ import annotations

import re
from dataclasses import dataclass

TITLE_MULTIPLIER = 1.5


@dataclass
class Rule:
    label: str
    pattern: re.Pattern
    weight: int


def _compile(item: dict) -> Rule:
    if "regex" in item:
        pat = item["regex"]
        label = item.get("label") or item["regex"][:25]
    else:
        term = item["term"]
        # whole-word match that also works for terms ending in symbols ("5+ years", "make.com")
        plural = r"(?:s|es)?" if term[-1:].isalpha() else ""  # "ai agent" also matches "ai agents"
        pat = r"(?<![\w])" + re.escape(term).replace(r"\ ", r"[\s\-]+") + plural + r"(?![\w])"
        label = item.get("label") or term
    return Rule(label=label, pattern=re.compile(pat, re.I), weight=int(item["weight"]))


class Scorer:
    def __init__(self, config: dict):
        self.positive = [_compile(i) for i in config.get("positive", [])]
        self.negative = [_compile(i) for i in config.get("negative", [])]

    def score(self, title: str, description: str) -> tuple[int, str, bool]:
        """Return (score 0-100, one-line reason, relevant?).

        relevant is True when at least one positive rule matched.
        """
        title = title or ""
        description = description or ""
        total = 0.0
        plus, minus = [], []
        for rule in self.positive + self.negative:
            in_title = bool(rule.pattern.search(title))
            in_desc = bool(rule.pattern.search(description))
            if not (in_title or in_desc):
                continue
            pts = rule.weight * (TITLE_MULTIPLIER if in_title else 1)
            total += pts
            tag = rule.label + ("*" if in_title else "")
            (plus if rule.weight > 0 else minus).append(tag)
        score = max(0, min(100, round(total)))
        parts = []
        if plus:
            parts.append("+ " + ", ".join(plus))
        if minus:
            parts.append("− " + ", ".join(minus))
        reason = " | ".join(parts) or "no keyword matches"
        return score, reason, bool(plus)
