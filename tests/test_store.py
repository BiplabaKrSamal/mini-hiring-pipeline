import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from pipeline.errors import Conflict, NotFound
from pipeline.stages import Stage
from pipeline.store import Store

S = Stage


def test_a_new_candidate_starts_in_applied(store, clock):
    c = store.add_candidate("Priya Sharma")
    assert c.stage == S.APPLIED and c.stage_since == clock.at
    assert [(e.from_stage, e.to_stage) for e in c.events] == [(None, S.APPLIED)]


def test_the_whole_path_is_recorded_in_order(store, clock):
    c = store.add_candidate("Priya Sharma")
    for stage in (S.SCREENING, S.INTERVIEW, S.OFFER, S.HIRED):
        clock.advance(days=2)
        c = store.move(c.id, stage, f"to {stage.value}")
        assert c.stage == stage and c.stage_since == clock.at
    assert [e.to_stage for e in c.events] == [S.APPLIED, S.SCREENING, S.INTERVIEW, S.OFFER, S.HIRED]
    assert c.events[-1].note == "to hired"


@pytest.mark.parametrize("path", [[], [S.SCREENING], [S.SCREENING, S.INTERVIEW], [S.SCREENING, S.INTERVIEW, S.OFFER]])
def test_rejection_is_possible_at_any_point_before_hired(store, path):
    c = store.add_candidate("Priya Sharma")
    for stage in path:
        c = store.move(c.id, stage)
    assert store.move(c.id, S.REJECTED, "Not a fit").stage == S.REJECTED


def test_skipping_and_going_back_are_refused_and_leave_no_trace(store):
    c = store.move(store.add_candidate("Priya Sharma").id, S.SCREENING)
    for bad in (S.OFFER, S.APPLIED, S.SCREENING):
        with pytest.raises(Conflict):
            store.move(c.id, bad)
    assert len(store.get(c.id).events) == 2


@pytest.mark.parametrize("final", [S.HIRED, S.REJECTED])
def test_a_final_outcome_cannot_be_reversed(store, final):
    c = store.add_candidate("Priya Sharma")
    for stage in (S.SCREENING, S.INTERVIEW, S.OFFER, final):
        c = store.move(c.id, stage)
    for target in Stage:
        with pytest.raises(Conflict):
            store.move(c.id, target)
    assert store.get(c.id).stage == final


def test_unknown_candidate(store):
    for call in (lambda: store.get(99), lambda: store.move(99, S.SCREENING)):
        with pytest.raises(NotFound):
            call()


def test_data_survives_reopening_the_file(store, tmp_path, clock):
    c = store.move(store.add_candidate("Priya Sharma").id, S.SCREENING, "booked")
    again = Store(str(tmp_path / "test.db"), now=clock).get(c.id)
    assert again.stage == S.SCREENING and again.events[-1].note == "booked"


def test_simultaneous_moves_let_exactly_one_through(store, tmp_path, clock):
    c = store.add_candidate("Priya Sharma")

    def attempt(_):
        try:
            Store(str(tmp_path / "test.db"), now=clock).move(c.id, S.SCREENING)
            return "moved"
        except Conflict:
            return "refused"

    with ThreadPoolExecutor(8) as pool:
        outcomes = list(pool.map(attempt, range(8)))
    assert outcomes.count("moved") == 1 and len(store.get(c.id).events) == 2


@pytest.mark.parametrize("sql", [
    "UPDATE events SET note = 'edited'",
    "UPDATE events SET to_stage = 'hired'",
    "DELETE FROM events",
    "UPDATE candidates SET name = 'Someone Else'",
    "DELETE FROM candidates",
    "INSERT OR REPLACE INTO events (id, candidate_id, to_stage, at) VALUES (2, 1, 'applied', 'x')",
    "REPLACE INTO candidates (id, name) VALUES (1, 'Someone Else')",
    "INSERT INTO events (id, candidate_id, to_stage, at) VALUES (2, 1, 'applied', 'x') ON CONFLICT(id) DO UPDATE SET note = 'edited'",
])
def test_the_database_itself_refuses_edits_and_deletes(store, tmp_path, sql):
    store.move(store.add_candidate("Priya Sharma").id, S.SCREENING)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        sqlite3.connect(str(tmp_path / "test.db")).execute(sql)
