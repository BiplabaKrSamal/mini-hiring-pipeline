"""Lengths of time, days and time windows, read in the recruiter's time zone."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .lexer import Tok

UTC = timezone.utc
DAY = 86400
UNIT_SECONDS = {"minute": 60, "hour": 3600, "day": DAY, "week": 7 * DAY, "month": 30 * DAY}
UNIT_WORDS = {unit + s: unit for unit in UNIT_SECONDS for s in ("", "s")}
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class QueryProblem(Exception):
    """Something in the query can't be read. The message is written for the recruiter."""


@dataclass(frozen=True)
class Clock:
    now: datetime      # timezone-aware, UTC
    tz: ZoneInfo

    @property
    def today(self) -> date:
        return self.now.astimezone(self.tz).date()

    def midnight(self, day: date) -> datetime:
        return datetime(day.year, day.month, day.day, tzinfo=self.tz).astimezone(UTC)

    def fmt_day(self, day: date) -> str:
        year = f" {day.year}" if day.year != self.today.year else ""
        return f"{_DAYS[day.weekday()]} {day.day} {_MONTHS[day.month - 1]}{year}"

    def fmt_moment(self, at: datetime) -> str:
        local = at.astimezone(self.tz)
        return f"{self.fmt_day(local.date())}, {local:%H:%M}"


def format_span(seconds: float) -> str:
    """9d 4h, 5h 10m, 42m: two units at most."""
    days, rest = divmod(max(0, int(seconds)), DAY)
    hours, rest = divmod(rest, 3600)
    if days:
        return f"{days}d {hours}h" if hours else f"{days}d"
    return f"{hours}h {rest // 60}m" if hours and rest // 60 else f"{hours}h" if hours else f"{rest // 60}m"


def _word(toks: list[Tok], i: int) -> str | None:
    return toks[i].text if 0 <= i < len(toks) and toks[i].kind == "word" else None


# -- lengths of time ----------------------------------------------------------

@dataclass(frozen=True)
class Duration:
    seconds: int
    phrase: str     # "3 days", "a week"
    unit: str
    count: int
    end: int        # index of the first token after it


def parse_duration(toks: list[Tok], i: int) -> Duration | None:
    word = _word(toks, i)
    if i < len(toks) and toks[i].kind == "num":
        count = int(toks[i].text)
    elif word in NUMBER_WORDS:
        count = NUMBER_WORDS[word]
    elif word in UNIT_WORDS:                                  # "over week" means one week
        return _duration(1, UNIT_WORDS[word], i + 1)
    else:
        return None
    unit = UNIT_WORDS.get(_word(toks, i + 1) or "")
    return _duration(count, unit, i + 2) if unit else None


def _duration(count: int, unit: str, end: int) -> Duration:
    phrase = f"{'an' if unit == 'hour' else 'a'} {unit}" if count == 1 else f"{count} {unit}s"
    return Duration(count * UNIT_SECONDS[unit], phrase, unit, count, end)


# -- days and windows ---------------------------------------------------------

@dataclass(frozen=True)
class Day:
    day: date
    at: datetime     # that day's midnight, in the recruiter's zone
    label: str
    end: int


def parse_day(toks: list[Tok], i: int, clock: Clock) -> Day | None:
    if i >= len(toks):
        return None
    t, today, name = toks[i], clock.today, None
    if t.kind == "iso":
        try:
            day = date(*map(int, t.text.split("-")))
        except ValueError:
            raise QueryProblem(f"\u201c{t.raw}\u201d isn't a real date.") from None
    elif _word(toks, i) == "today":
        day, name = today, "today"
    elif _word(toks, i) == "yesterday":
        day, name = today - timedelta(days=1), "yesterday"
    elif _word(toks, i) == "tomorrow":
        raise QueryProblem("Tomorrow hasn't happened yet, so nothing can be dated from it.")
    elif _word(toks, i) in WEEKDAYS:                          # the most recent one, today included
        day = today - timedelta(days=(today.weekday() - WEEKDAYS[t.text]) % 7)
    else:
        return None
    label = clock.fmt_day(day) if name is None else f"{name} ({clock.fmt_day(day)})"
    return Day(day, clock.midnight(day), label, i + 1)


@dataclass(frozen=True)
class TimeWindow:
    start: datetime | None
    end: datetime | None     # exclusive
    label: str

    def contains(self, at: datetime) -> bool:
        return (self.start is None or at >= self.start) and (self.end is None or at < self.end)

    def intersect(self, other: "TimeWindow") -> "TimeWindow":
        starts = [s for s in (self.start, other.start) if s]
        ends = [e for e in (self.end, other.end) if e]
        return TimeWindow(max(starts, default=None), min(ends, default=None), f"{self.label} and {other.label}")


def parse_window(toks: list[Tok], i: int, clock: Clock) -> tuple[TimeWindow, int] | None:
    """Reads a time phrase starting at i, or returns None if there isn't one."""
    word = _word(toks, i)
    next_day = lambda d: clock.midnight(d.day + timedelta(days=1))

    if word in ("since", "after", "before"):
        day = parse_day(toks, i + 1, clock)
        if day is None:
            raise QueryProblem(f"\u201c{word}\u201d needs a day or date after it, like \u201c{word} Monday\u201d or \u201c{word} 2026-09-28\u201d.")
        if word == "before":
            return TimeWindow(None, day.at, f"before {day.label}"), day.end
        start = next_day(day) if word == "after" else day.at
        if start > clock.now:
            raise QueryProblem(f"{day.label} is still in the future, so nothing can have happened since then.")
        return TimeWindow(start, None, f"{word} {day.label}"), day.end

    if word in ("today", "yesterday"):
        day = parse_day(toks, i, clock)
        return TimeWindow(day.at, next_day(day), day.label), day.end

    if word in ("this", "last") and _word(toks, i + 1) == "week":
        monday = clock.today - timedelta(days=clock.today.weekday())
        if word == "this":
            return TimeWindow(clock.midnight(monday), None, f"this week (from {clock.fmt_day(monday)})"), i + 2
        previous = monday - timedelta(days=7)
        label = f"last week ({clock.fmt_day(previous)} to {clock.fmt_day(monday - timedelta(days=1))})"
        return TimeWindow(clock.midnight(previous), clock.midnight(monday), label), i + 2

    # rolling: "in the last 3 days", "past week", "within 2 weeks"
    j = i + 1 if word in ("in", "within", "over", "during", "for") else i
    if _word(toks, j) == "the":
        j += 1
    if _word(toks, j) in ("last", "past"):
        j += 1
    elif word != "within":
        return None
    dur = parse_duration(toks, j)
    if dur is None:
        return None
    what = dur.unit if dur.count == 1 else dur.phrase
    return TimeWindow(clock.now - timedelta(seconds=dur.seconds), None, f"in the last {what}"), dur.end
