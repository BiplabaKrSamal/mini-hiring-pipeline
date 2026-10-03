"""The behaviours the assignment asks for, on the demo data (scripts/seed.py backdates it from NOW)."""
import pytest

from pipeline.errors import Invalid
from pipeline.search import run
from pipeline.search.parser import Entered, InStage, InStageFor, parse
from pipeline.search.when import Clock
from pipeline.stages import Stage
from scripts.seed import build
from zoneinfo import ZoneInfo
from conftest import NOW

S = Stage


@pytest.fixture(scope="module")
def people(tmp_path_factory):
    return build(str(tmp_path_factory.mktemp("demo") / "demo.db"), NOW).all()


def ask(people, query, tz="Asia/Kolkata"):
    return run(query, people, NOW, tz)


def names(result):
    return [h.candidate.name for h in result.hits]


def codes(result):
    return {n.code for n in result.notices}


# -- the examples from the brief ----------------------------------------------

def test_find_a_person(people):
    r = ask(people, "Find Priya Sharma")
    assert names(r) == ["Priya Sharma", "Rahul Sharma", "Priyanka Shah"]       # both names, then one, then a prefix
    assert r.hits[0].score == 100


def test_a_typo_still_finds_the_person_and_a_swapped_pair_beats_a_wrong_letter(people):
    r = ask(people, "sharam")
    assert set(names(r)[:2]) == {"Priya Sharma", "Rahul Sharma"} and names(r)[2] == "Sharan Iyer"
    assert "typo" in r.hits[0].reasons[0]


def test_whos_in_interview(people):
    r = ask(people, "Who's in Interview right now?")
    assert names(r) == ["Vikram Singh", "Sharan Iyer", "Aarav Mehta", "Karan Malhotra"]      # waiting longest first


def test_stuck_in_screening_for_more_than_a_week(people):
    r = ask(people, "Who has been stuck in Screening for more than a week?")
    assert names(r) == ["Priya Sharma", "Rahul Sharma"] and not r.notices


def test_moved_to_interview_since_monday(people):
    r = ask(people, "Who moved to Interview since Monday?")
    assert names(r) == ["Karan Malhotra", "Aarav Mehta", "Sharan Iyer"]                      # newest first; Vikram moved 11 days ago
    assert all(h.reasons[0].startswith("Moved to Interview") for h in r.hits)


def test_reached_offer_but_did_not_get_hired(people):
    r = ask(people, "Who reached the Offer stage but didn't get hired?")
    assert set(names(r)) == {"Kabir Anand", "Tara Bose", "Arjun Reddy"}                     # Siddharth and Lakshmi were hired
    assert {h.candidate.stage for h in r.hits} == {S.REJECTED, S.OFFER}


def test_everyone_except_rejected(people):
    r = ask(people, "Everyone except rejected candidates.")
    assert len(r.hits) == 12 and S.REJECTED not in {h.candidate.stage for h in r.hits}


# -- combining, ranking -------------------------------------------------------

def test_conditions_combine(people):
    assert names(ask(people, "priya in screening for more than 5 days")) == ["Priya Sharma"]
    assert names(ask(people, "stuck in interview")) == ["Vikram Singh"]


def test_stage_lists_and_negated_names(people):
    assert len(ask(people, "interview or offer").hits) == 5
    r = ask(people, "everyone except priya")
    assert len(r.hits) == 14 and not {"Priya Sharma", "Priyanka Shah"} & set(names(r))


def test_a_negation_covers_the_whole_list(people):
    r = ask(people, "everyone except rejected and hired")
    assert len(r.hits) == 10 and not {S.REJECTED, S.HIRED} & {h.candidate.stage for h in r.hits}


def test_not_stuck_negates_stuck_not_the_stage(people):
    assert names(ask(people, "not stuck in screening")) == ["Priyanka Shah"]      # in Screening, but not for a week


def test_yesterday_depends_on_the_users_time_zone(people):
    assert names(ask(people, "moved yesterday", "Asia/Kolkata")) == ["Karan Malhotra", "Aarav Mehta"]
    assert names(ask(people, "moved yesterday", "UTC")) == ["Aarav Mehta"]       # still Wednesday there, so Karan's move is "today"


def test_an_unknown_time_zone_is_refused(people):
    with pytest.raises(Invalid, match="time zone"):
        ask(people, "hired", "Mars/Base")


# -- queries that don't make sense: she is told why, not shown a blank --------

def test_nonsense_is_explained(people):
    r = ask(people, "xqzv")
    assert r.hits == [] and "no_match" in codes(r) and r.empty_reason


def test_unknown_words_are_dropped_with_a_warning_and_the_rest_still_runs(people):
    r = ask(people, "priya xqzv")
    assert names(r)[0] == "Priya Sharma" and "left it out" in next(n.message for n in r.notices if n.code == "no_match")


@pytest.mark.parametrize("query, code", [
    ("stuck in hired", "stuck_in_final"),
    ("in screening in interview", "impossible_stages"),
    ("since tomorrow", "bad_time"),
    ("since 2027-01-01", "bad_time"),
    ("more than", "needs_duration"),
])
def test_impossible_queries_return_nothing_and_an_error(people, query, code):
    r = ask(people, query)
    assert r.hits == [] and code in codes(r) and r.empty_reason
    assert any(n.level == "error" for n in r.notices)


@pytest.mark.parametrize("query, code", [("who is the", "nothing_to_search"), ("stuck for 5", "stray_number"), ("stuck in screening or moved since monday", "or_unsupported")])
def test_other_things_it_cannot_read_are_called_out(people, query, code):
    assert code in codes(ask(people, query))


def test_a_blank_box_just_browses(people):
    assert ask(people, "   ").mode == "browse"


def test_an_empty_answer_says_which_condition_failed(people):
    r = ask(people, "stuck in screening for more than 2 weeks")
    assert r.hits == [] and "Nobody matches" in r.empty_reason and "9d 4h (Priya Sharma)" in r.empty_reason
    assert "Each condition matches" in ask(people, "in hired and moved yesterday").empty_reason


def test_the_reading_is_shown_back(people):
    assert [i["text"] for i in ask(people, "who moved to interview since monday").interpretation] == ["Moved to Interview since Mon 28 Sep"]
    assert ask(people, "not hired").interpretation == [{"text": "Not in Hired", "negated": True}]


# -- vocabulary ---------------------------------------------------------------

CLOCK = Clock(NOW, ZoneInfo("UTC"))


@pytest.mark.parametrize("text, expected", [
    ("in screening", InStage(frozenset({S.SCREENING}))),
    ("at the offer stage", InStage(frozenset({S.OFFER}))),
    ("interviewing", InStage(frozenset({S.INTERVIEW}))),
    ("screening, interview or offer", InStage(frozenset({S.SCREENING, S.INTERVIEW, S.OFFER}))),
    ("not hired", InStage(frozenset({S.HIRED}), negated=True)),
    ("except rejected and hired", InStage(frozenset({S.REJECTED, S.HIRED}), negated=True)),
    ("not stuck", InStageFor(">", 7 * 86400, "7 days", stuck=True, negated=True)),
    ("excluding rejected", InStage(frozenset({S.REJECTED}), negated=True)),
    ("didn't get hired", InStage(frozenset({S.HIRED}), negated=True)),
    ("reached offer", Entered(S.OFFER)),
    ("went through screening", Entered(S.SCREENING)),
    ("never reached offer", Entered(S.OFFER, negated=True)),
    ("more than 3 days", InStageFor(">", 3 * 86400, "3 days")),
    ("at least a week", InStageFor(">=", 7 * 86400, "a week")),
    ("for 2 days", InStageFor(">=", 2 * 86400, "2 days")),
    ("less than 48 hours", InStageFor("<", 48 * 3600, "48 hours")),
])
def test_how_things_are_phrased(text, expected):
    assert parse(text, CLOCK).clauses == [expected]
