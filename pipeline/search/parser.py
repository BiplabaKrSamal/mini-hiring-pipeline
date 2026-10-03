"""Reads a search-box sentence into conditions.

A small hand-written grammar, not a model: the same text always reads the same way,
and anything it can't read is reported back instead of guessed at.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from ..stages import BOARD_ORDER, FINAL, Stage
from .lexer import Tok, tokenize
from .when import WEEKDAYS, Clock, QueryProblem, TimeWindow, parse_duration, parse_window

STUCK_AFTER = 7 * 86400     # what "stuck" means when no length of time is given

STAGE_WORDS = {
    "applied": Stage.APPLIED,
    "screening": Stage.SCREENING, "screen": Stage.SCREENING,
    "interview": Stage.INTERVIEW, "interviews": Stage.INTERVIEW, "interviewing": Stage.INTERVIEW,
    "offer": Stage.OFFER, "offers": Stage.OFFER,
    "hired": Stage.HIRED, "hire": Stage.HIRED,
    "rejected": Stage.REJECTED, "reject": Stage.REJECTED,
}
MOVE_VERBS = {"moved", "move", "advanced"}                          # "moved since Monday" needs no stage
REACH_VERBS = MOVE_VERBS | {"reached", "reach", "went", "entered", "got"}
GLUE = {"to", "into", "through", "the", "a"}                        # "moved to the interview stage"
NEGATORS = {"not", "except", "excluding", "without", "never", "isnt", "arent", "wasnt", "werent",
            "didnt", "doesnt", "dont", "hasnt", "havent"}
STUCK = {"stuck", "stalled"}
EVERYONE = {"everyone", "everybody", "all", "anyone"}
FILLER = EVERYONE | set("""
who whos whom which what whats is are was were be been being am the a an of to for with that these those
has have had do does did it its them they their me my us we show list find get see display search give tell
please candidate candidates people person applicant applicants someone currently now right stage but and
also then yet still just only ever already far so there here at in on from by as out up this
reached reach got went entered
""".split())
COMPARATORS = sorted([
    (("more", "than"), ">"), (("longer", "than"), ">"), (("over",), ">"),
    (("at", "least"), ">="), (("for",), ">="),
    (("less", "than"), "<"), (("under",), "<"),
], key=lambda c: -len(c[0]))
_OP_WORDS = {">": "more than", ">=": "at least", "<": "less than"}
_DAY_WORDS = set(WEEKDAYS) | {"today", "yesterday", "tomorrow"}


def _names(stages) -> str:
    labels = [s.label for s in sorted(stages, key=BOARD_ORDER.index)]
    return labels[0] if len(labels) == 1 else f"{', '.join(labels[:-1])} or {labels[-1]}"


# -- conditions --------------------------------------------------------------

@dataclass(frozen=True)
class InStage:
    """Currently in one of these stages (and, with a window, arrived in it)."""
    stages: frozenset[Stage]
    window: TimeWindow | None = None
    negated: bool = False

    def describe(self) -> str:
        when = f", arrived {self.window.label}" if self.window else ""
        return f"{'Not in' if self.negated else 'In'} {_names(self.stages)}{when}"


@dataclass(frozen=True)
class Entered:
    """Has moved into this stage at some point, optionally within a window."""
    stage: Stage
    window: TimeWindow | None = None
    negated: bool = False

    def describe(self) -> str:
        when = f" {self.window.label}" if self.window else ""
        if self.negated:
            return f"Did not move to {self.stage.label}{when}" if self.window else f"Never reached {self.stage.label}"
        return f"Moved to {self.stage.label}{when}" if self.window else f"Reached {self.stage.label}"


@dataclass(frozen=True)
class InStageFor:
    """How long they have been in their current stage."""
    op: str
    seconds: int
    phrase: str
    stuck: bool = False
    negated: bool = False

    def describe(self) -> str:
        text = f"{'stuck' if self.stuck else 'in the same stage'} for {_OP_WORDS[self.op]} {self.phrase}"
        return f"Not {text}" if self.negated else text.capitalize()


@dataclass(frozen=True)
class Moved:
    """Changed stage at all, optionally within a window."""
    window: TimeWindow | None = None
    negated: bool = False

    def describe(self) -> str:
        when = f" {self.window.label}" if self.window else ""
        return ("Has not moved" if self.negated else "Moved stage") + when


@dataclass(frozen=True)
class Text:
    """A name fragment, matched loosely."""
    term: str
    negated: bool = False

    def describe(self) -> str:
        return f"Name {'is not like' if self.negated else 'matches'} \u201c{self.term}\u201d"


@dataclass(frozen=True)
class Notice:
    level: str     # info | warning | error
    code: str
    message: str


@dataclass
class Parsed:
    clauses: list = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)
    blank: bool = False        # nothing was typed
    everyone: bool = False     # "everyone", "all candidates"

    @property
    def errors(self) -> list[Notice]:
        return [n for n in self.notices if n.level == "error"]


# -- scanner ------------------------------------------------------------------

class _Scanner:
    def __init__(self, toks: list[Tok], clock: Clock):
        self.toks, self.clock = toks, clock
        self.i = 0
        self.out = Parsed()
        self.negate = False
        self.stuck = False
        self.negate_stuck = False
        self.waiting: TimeWindow | None = None    # a time phrase that hasn't found its condition yet
        self.saw_or = False

    def word(self, i: int) -> str | None:
        return self.toks[i].text if 0 <= i < len(self.toks) and self.toks[i].kind == "word" else None

    def note(self, level: str, code: str, message: str) -> None:
        self.out.notices.append(Notice(level, code, message))

    def stage_at(self, i: int) -> tuple[Stage, int] | None:
        j = i + 1 if self.word(i) == "the" else i
        stage = STAGE_WORDS.get(self.word(j) or "")
        if stage is None:
            return None
        return stage, j + 2 if self.word(j + 1) == "stage" else j + 1

    def stage_list(self, i: int) -> tuple[frozenset[Stage], int] | None:
        """"interview", "interview or offer", "screening, interview"."""
        first = self.stage_at(i)
        if first is None:
            return None
        stages, end = {first[0]}, first[1]
        joiners = ("or", "and") if self.negate else ("or",)      # "except rejected and hired" excludes both
        while end < len(self.toks) and (self.toks[end].kind == "comma" or self.word(end) in joiners):
            more = self.stage_at(end + 1)
            if more is None:
                break
            stages.add(more[0])
            end = more[1]
        return frozenset(stages), end

    def emit(self, clause) -> None:
        if self.negate:
            clause, self.negate = replace(clause, negated=True), False
        if self.waiting and hasattr(clause, "window") and clause.window is None:
            clause, self.waiting = replace(clause, window=self.waiting), None
        self.out.clauses.append(clause)

    def attach(self, window: TimeWindow) -> None:
        """A time phrase belongs to the nearest condition before it, or the next one after."""
        for k in range(len(self.out.clauses) - 1, -1, -1):
            c = self.out.clauses[k]
            if hasattr(c, "window"):
                self.out.clauses[k] = replace(c, window=window if c.window is None else c.window.intersect(window))
                return
        self.waiting = window if self.waiting is None else self.waiting.intersect(window)

    def comparator(self) -> tuple[str, int, str] | None:
        for words, op in COMPARATORS:
            if all(self.word(self.i + k) == w for k, w in enumerate(words)):
                return op, self.i + len(words), " ".join(words)
        return None

    # -- one step of the scan; returns True if it used up tokens
    def step(self) -> bool:
        w = self.word(self.i)
        if self.toks[self.i].kind == "comma":
            self.i += 1
        elif w in NEGATORS:
            self.negate, self.i = True, self.i + 1
        elif w in STUCK:
            self.stuck, self.negate_stuck, self.negate, self.i = True, self.negate, False, self.i + 1
        elif w in REACH_VERBS and self.reach(w):
            pass
        elif (found := self.stage_list(self.i + 1 if w in ("in", "at", "on") else self.i)):
            self.emit(InStage(found[0]))
            self.i = found[1]
        elif self.duration():
            pass
        elif self.time_window():
            pass
        elif w == "or":
            self.saw_or, self.i = True, self.i + 1
        elif w in FILLER:
            self.out.everyone |= w in EVERYONE
            self.i += 1
        else:
            return False
        return True

    def reach(self, verb: str) -> bool:
        """"reached the Offer stage", "moved to Interview", "went through Screening"."""
        j = self.i + 1
        while self.word(j) in GLUE:
            j += 1
        found = self.stage_at(j)
        if found:
            self.emit(Entered(found[0]))
            self.i = found[1]
        elif verb in MOVE_VERBS:
            self.emit(Moved())
            self.i += 1
        else:
            return False
        return True

    def duration(self) -> bool:
        """"more than a week", "for 3 days", "at least 2 weeks"."""
        found = self.comparator()
        if found is None:
            return False
        op, k, spoken = found
        if self.word(k) in ("the", "last", "past"):                 # "over the last 3 days" is a time window
            return False
        dur = parse_duration(self.toks, k)
        if dur is None:
            if spoken == "for":                                     # an ordinary word here
                return False
            self.note("error", "needs_duration",
                      f"\u201c{spoken}\u201d needs a length of time after it, like \u201c{spoken} 3 days\u201d or \u201c{spoken} a week\u201d.")
            self.i = k
            return True
        self.emit(InStageFor(op, dur.seconds, dur.phrase, self.stuck, self.negate_stuck))
        self.stuck = self.negate_stuck = False
        self.i = dur.end
        return True

    def time_window(self) -> bool:
        try:
            found = parse_window(self.toks, self.i, self.clock)
        except QueryProblem as problem:
            self.note("error", "bad_time", str(problem))
            self.i += 1
            # skip the rest of the phrase so "tomorrow" isn't then searched for as a name
            while self.i < len(self.toks) and (self.toks[self.i].kind in ("iso", "num") or self.word(self.i) in _DAY_WORDS):
                self.i += 1
            return True
        if found is None:
            return False
        self.attach(found[0])
        self.i = found[1]
        return True

    def leftover(self) -> None:
        t = self.toks[self.i]
        self.i += 1
        if t.kind == "word":
            self.emit(Text(t.text))
        elif t.kind == "num":
            self.note("warning", "stray_number",
                      f"I don't know what \u201c{t.raw}\u201d refers to. A length of time needs a unit, like \u201cmore than {t.raw} days\u201d.")
        elif t.kind == "iso":
            self.note("warning", "stray_date", f"A date needs a word in front of it, like \u201csince {t.raw}\u201d or \u201cbefore {t.raw}\u201d.")

    def run(self) -> Parsed:
        while self.i < len(self.toks):
            if not self.step():
                self.leftover()
        out = self.out
        if self.stuck and not any(isinstance(c, InStageFor) for c in out.clauses):
            self.emit(InStageFor(">", STUCK_AFTER, "7 days", True, self.negate_stuck))
            self.note("info", "stuck_default", "\u201cStuck\u201d on its own means more than 7 days in the current stage. Add a length of time to change that, like \u201cstuck for 3 days\u201d.")
        if self.waiting:
            out.clauses.append(Moved(self.waiting))
            self.note("info", "window_alone", f"Read \u201c{self.waiting.label}\u201d as \u201cmoved {self.waiting.label}\u201d.")
        if self.saw_or and any(not isinstance(c, Text) for c in out.clauses):
            self.note("warning", "or_unsupported", "Conditions are combined with \u201cand\u201d. \u201cor\u201d only works between stages (\u201cin Screening or Interview\u201d) or names.")
        self.check()
        return out

    def check(self) -> None:
        """Combinations that can never match anyone are explained rather than searched."""
        places = [c for c in self.out.clauses if isinstance(c, InStage) and not c.negated]
        if len(places) > 1 and not frozenset.intersection(*(c.stages for c in places)):
            a, b = places[0].stages, places[1].stages
            self.note("error", "impossible_stages",
                      f"Nobody can be in {_names(a)} and in {_names(b)} at the same time. To see both, write \u201c{_names(a | b).lower()}\u201d.")
        for c in self.out.clauses:
            if isinstance(c, InStageFor) and c.stuck and not c.negated and places and all(s in FINAL for p in places for s in p.stages):
                self.note("error", "stuck_in_final", f"{_names(places[0].stages)} is a final outcome, so nobody can be stuck there. \u201cStuck\u201d applies to Applied through Offer.")


def parse(query: str, clock: Clock) -> Parsed:
    toks = tokenize(query)
    if not toks:
        return Parsed(blank=True)
    parsed = _Scanner(toks, clock).run()
    if not parsed.clauses and not parsed.everyone and not parsed.notices:
        parsed.notices.append(Notice("info", "nothing_to_search",
                                     "There's nothing to search for yet. Try a name, a stage (\u201cin Interview\u201d), or a time (\u201cstuck for more than a week\u201d)."))
    return parsed
