"""Runs a parsed query over the candidates: filter, rank, explain."""
from __future__ import annotations

import operator
import re
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..errors import Invalid
from ..store import Candidate
from .fuzzy import best_match, fold, words
from .parser import Entered, InStage, InStageFor, Moved, Notice, Text, parse
from .when import Clock, format_span

_COMPARE = {">": operator.gt, ">=": operator.ge, "<": operator.lt}


@dataclass
class Hit:
    candidate: Candidate
    score: float                     # name match, 0-100 (0 when no name was typed)
    reasons: list[str]


@dataclass
class SearchResult:
    query: str
    mode: str                        # "browse" when the box is empty
    interpretation: list[dict] = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    order: str = ""
    empty_reason: str | None = None


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        raise Invalid(f"Unknown time zone \u201c{name}\u201d. Use a name like Asia/Kolkata or UTC.") from None


def _match_name(term: Text, c: Candidate) -> tuple[float, str] | None:
    m = best_match(term.term, words(c.name))
    if m is None:
        return None
    shown = next((w for w in re.split(r"\W+", c.name) if fold(w) == m.token), m.token)
    return m.score, {
        "exact": f"Name has \u201c{shown}\u201d",
        "prefix": f"Name starts with \u201c{term.term}\u201d",
        "typo": f"\u201c{term.term}\u201d is close to {shown} (typo)",
        "inside": f"Name contains \u201c{term.term}\u201d",
    }[m.kind]


def holds(clause, c: Candidate, now: datetime) -> bool:
    if isinstance(clause, InStage):
        ok = c.stage in clause.stages and (clause.window is None or clause.window.contains(c.stage_since))
    elif isinstance(clause, Entered):
        ok = any(e.to_stage == clause.stage and (clause.window is None or clause.window.contains(e.at)) for e in c.events)
    elif isinstance(clause, InStageFor):
        ok = _COMPARE[clause.op]((now - c.stage_since).total_seconds(), clause.seconds) and not (clause.stuck and c.stage.is_final)
    else:
        ok = any(e.from_stage and (clause.window is None or clause.window.contains(e.at)) for e in c.events)
    return ok != clause.negated


def _when_reason(clause, c: Candidate, clock: Clock) -> str | None:
    if isinstance(clause, Entered) and not clause.negated:
        e = next(e for e in reversed(c.events) if e.to_stage == clause.stage and (clause.window is None or clause.window.contains(e.at)))
        return f"{'Applied' if e.from_stage is None else 'Moved to ' + e.to_stage.label} {clock.fmt_moment(e.at)}"
    return None


def _order(filters) -> str:
    """How to break ties between equally good name matches (or the whole order, when no name was typed)."""
    positive = [c for c in filters if not c.negated]
    if any(isinstance(c, InStageFor) for c in positive):
        return "longest in stage first"
    if any(isinstance(c, (Entered, Moved)) or getattr(c, "window", None) for c in positive):
        return "most recent activity first"
    places = [c for c in positive if isinstance(c, InStage)]
    if places and all(not s.is_final for p in places for s in p.stages):
        return "longest in stage first"
    return "most recent activity first"


def _explain_empty(filters, typed_a_name: bool, people: list[Candidate], now: datetime) -> str:
    for cl in filters:
        if not any(holds(cl, c, now) for c in people):
            said = cl.describe()
            text, hint = f"Nobody matches \u201c{said[0].lower() + said[1:]}\u201d.", ""
            if isinstance(cl, InStageFor) and not cl.negated:
                rest = [o for o in filters if o is not cl]
                waiting = [c for c in people if not c.stage.is_final and all(holds(o, c, now) for o in rest)]
                if waiting:
                    slowest = min(waiting, key=lambda c: c.stage_since)
                    hint = f" The longest anyone has been in their current stage is {format_span((now - slowest.stage_since).total_seconds())} ({slowest.name})."
            return text + hint
    if len(filters) + typed_a_name > 1:
        return "Each condition matches someone on its own, but nobody matches all of them."
    return "Nobody matches."


def run(query: str, people: list[Candidate], now: datetime, tz: str = "UTC") -> SearchResult:
    clock = Clock(now, zone(tz))
    parsed = parse(query, clock)
    if parsed.blank:
        return SearchResult(query, "browse")

    result = SearchResult(query, "search", notices=list(parsed.notices))
    filters = [c for c in parsed.clauses if not isinstance(c, Text)]

    wanted: list[tuple[Text, dict]] = []     # name terms somebody matches
    unwanted: list[dict] = []                # names to leave out
    dead: list[Text] = []                    # name terms nobody matches
    for t in (c for c in parsed.clauses if isinstance(c, Text)):
        matches = {c.id: _match_name(t, c) for c in people}
        if not any(matches.values()):
            dead.append(t)
        elif t.negated:
            unwanted.append({k: m for k, m in matches.items() if m and m[0] >= 50})    # only close matches may exclude someone
        else:
            wanted.append((t, matches))
    for t in dead:
        result.notices.append(Notice(
            "warning", "no_match",
            f"No one is named anything like \u201c{t.term}\u201d, and it isn't a stage, date or length of time I know."
            + (" I left it out and searched on the rest." if filters or wanted or unwanted else ""),
        ))
    result.interpretation = [{"text": c.describe(), "negated": c.negated} for c in parsed.clauses if c not in dead]

    if parsed.errors:
        result.notices = [n for n in result.notices if n.level == "error"]     # assumptions don't matter when the query can't run
        result.empty_reason = "This search can't match anyone as written. The note above says what to change."
        return result
    if not (filters or wanted or unwanted or parsed.everyone):
        result.empty_reason = "I couldn't turn that into a search."
        return result

    order = _order(filters)
    result.order = ("best name match first, then " if wanted else "") + order
    for c in people:
        if not all(holds(cl, c, now) for cl in filters) or any(m.get(c.id) for m in unwanted):
            continue
        found = [m[c.id] for _, m in wanted]
        if wanted and not any(found):
            continue
        reasons = [m[1] for m in found if m] + [r for r in (_when_reason(cl, c, clock) for cl in filters) if r]
        result.hits.append(Hit(c, round(sum(m[0] if m else 0 for m in found) / len(found), 1) if found else 0.0, reasons))

    oldest = order == "longest in stage first"
    result.hits.sort(key=lambda h: (-h.score, h.candidate.stage_since.timestamp() * (1 if oldest else -1), h.candidate.name.lower(), h.candidate.id))
    if not result.hits:
        result.empty_reason = _explain_empty(filters, bool(wanted), people, now)
    return result
