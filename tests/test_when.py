from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from pipeline.search.lexer import tokenize
from pipeline.search.when import Clock, QueryProblem, format_span, parse_duration, parse_window
from conftest import NOW

KOLKATA = Clock(NOW, ZoneInfo("Asia/Kolkata"))                                                  # Thu 1 Oct, 00:09
PACIFIC = Clock(datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc), ZoneInfo("America/Los_Angeles"))  # Wed 30 Sep, 20:00


def window(text, clock=KOLKATA):
    return parse_window(tokenize(text), 0, clock)[0]


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_since_monday_starts_at_midnight_in_the_users_zone():
    assert window("since Monday").start == utc(2026, 9, 27, 18, 30)           # Mon 00:00 in Kolkata
    assert window("since Monday", PACIFIC).start == utc(2026, 9, 28, 7, 0)    # Mon 00:00 in Los Angeles


def test_today_and_yesterday_follow_the_local_date_not_the_utc_date():
    # it is already Thursday in Kolkata while UTC still says Wednesday
    assert window("today").start == utc(2026, 9, 30, 18, 30)
    assert (window("yesterday").start, window("yesterday").end) == (utc(2026, 9, 29, 18, 30), utc(2026, 9, 30, 18, 30))


def test_since_includes_the_day_after_does_not():
    assert window("since 2026-09-28").start == utc(2026, 9, 27, 18, 30)
    assert window("after 2026-09-28").start == utc(2026, 9, 28, 18, 30)
    assert window("before 2026-09-28").end == utc(2026, 9, 27, 18, 30)


def test_last_week_is_the_previous_calendar_week_and_past_week_is_rolling():
    assert (window("last week").start, window("last week").end) == (utc(2026, 9, 20, 18, 30), utc(2026, 9, 27, 18, 30))
    assert window("past week").start == utc(2026, 9, 23, 18, 39) and window("past week").label == "in the last week"
    assert window("in the last 3 days").start == utc(2026, 9, 27, 18, 39)


@pytest.mark.parametrize("text, message", [
    ("since tomorrow", "hasn't happened"),
    ("since 2027-01-01", "future"),
    ("since 2026-02-30", "real date"),
    ("since", "needs a day or date"),
])
def test_unreadable_times_say_why(text, message):
    with pytest.raises(QueryProblem, match=message):
        parse_window(tokenize(text), 0, KOLKATA)


def test_ordinary_words_are_not_times():
    assert parse_window(tokenize("interview"), 0, KOLKATA) is None


@pytest.mark.parametrize("text, seconds", [("a week", 7 * 86400), ("2 weeks", 14 * 86400), ("3 days", 3 * 86400), ("an hour", 3600), ("two months", 60 * 86400)])
def test_durations(text, seconds):
    assert parse_duration(tokenize(text), 0).seconds == seconds


def test_a_number_without_a_unit_is_not_a_duration():
    assert parse_duration(tokenize("10"), 0) is None


@pytest.mark.parametrize("seconds, text", [(0, "0m"), (180, "3m"), (3600, "1h"), (5 * 3600 + 600, "5h 10m"), (86400, "1d"), (9 * 86400 + 4 * 3600, "9d 4h")])
def test_format_span(seconds, text):
    assert format_span(seconds) == text
