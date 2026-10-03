"""Name matching that forgives typing slips."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def fold(text: str) -> str:
    """Lowercase, no accents or apostrophes: "Zoë O'Brien" -> "zoe obrien"."""
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return text.lower().replace("’", "").replace("'", "")


def words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", fold(text)) if w]


def distance(a: str, b: str) -> float:
    """Edit distance, where swapping two neighbours costs 0.75 instead of 1.

    Swapped letters are the commonest typing slip ("sharam" for "sharma"), so they
    should rank above an unrelated one-letter difference ("sharan").
    """
    if a == b:
        return 0.0
    if not a or not b:
        return float(max(len(a), len(b)))
    older, prev = None, [float(j) for j in range(len(b) + 1)]
    for i in range(1, len(a) + 1):
        cur = [float(i)] + [0.0] * len(b)
        for j in range(1, len(b) + 1):
            best = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                best = min(best, older[j - 2] + 0.75)
            cur[j] = best
        older, prev = prev, cur
    return prev[-1]


@dataclass(frozen=True)
class Match:
    score: float   # 0-100
    kind: str      # exact | prefix | typo | inside
    token: str


def match(term: str, token: str) -> Match | None:
    if term == token:
        return Match(100.0, "exact", token)
    if token.startswith(term):                        # "pri" -> Priya; a lone letter is an initial
        return Match(40.0 if len(term) == 1 else 75 + 20 * len(term) / len(token), "prefix", token)
    budget = 0 if len(term) <= 3 else 1 if len(term) <= 7 else 2    # short words get no slack, or "ann" matches everyone
    cost = distance(term, token)
    if cost <= budget:
        return Match(70 - 20 * cost, "typo", token)
    if len(term) >= 3 and term in token:
        return Match(45.0, "inside", token)
    return None


def best_match(term: str, tokens: list[str]) -> Match | None:
    found = [m for m in (match(term, t) for t in tokens) if m]
    return max(found, key=lambda m: m.score) if found else None
