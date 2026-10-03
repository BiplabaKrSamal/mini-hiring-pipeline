"""SQLite storage.

Both tables are insert-only: triggers abort every UPDATE, every DELETE, and any INSERT
that would replace an existing row, so the history can't be edited even by code that tries. A candidate's stage is never stored. It is
whatever their latest event says, so the stage and the history can't disagree.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterator

from .errors import NotFound
from .stages import Stage, check_move

UTC = timezone.utc
Clock = Callable[[], datetime]
_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_STAGES = ", ".join(f"'{s.value}'" for s in Stage)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS candidates (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK (length(name) > 0)
);
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id),
    from_stage   TEXT CHECK (from_stage IN ({_STAGES})),
    to_stage     TEXT NOT NULL CHECK (to_stage IN ({_STAGES})),
    note         TEXT NOT NULL DEFAULT '',
    at           TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'the history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'the history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS candidates_no_update BEFORE UPDATE ON candidates
BEGIN SELECT RAISE(ABORT, 'candidates are append-only'); END;
CREATE TRIGGER IF NOT EXISTS candidates_no_delete BEFORE DELETE ON candidates
BEGIN SELECT RAISE(ABORT, 'candidates are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_replace BEFORE INSERT ON events
WHEN EXISTS (SELECT 1 FROM events WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'the history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS candidates_no_replace BEFORE INSERT ON candidates
WHEN EXISTS (SELECT 1 FROM candidates WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'candidates are append-only'); END;
"""


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def to_text(at: datetime) -> str:
    return at.astimezone(UTC).strftime(_FORMAT)


def from_text(text: str) -> datetime:
    return datetime.strptime(text, _FORMAT).replace(tzinfo=UTC)


@dataclass(frozen=True)
class Event:
    from_stage: Stage | None
    to_stage: Stage
    note: str
    at: datetime


@dataclass(frozen=True)
class Candidate:
    id: int
    name: str
    events: tuple[Event, ...]

    @property
    def stage(self) -> Stage:
        return self.events[-1].to_stage

    @property
    def stage_since(self) -> datetime:
        return self.events[-1].at


class Store:
    def __init__(self, path: str, now: Clock = utcnow):
        self.path, self.now = str(path), now
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        """One writer at a time, so checking the current stage and recording the move can't interleave."""
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def add_candidate(self, name: str) -> Candidate:
        at = to_text(self.now())
        with self._write() as db:
            cid = db.execute("INSERT INTO candidates (name) VALUES (?)", (name,)).lastrowid
            db.execute("INSERT INTO events (candidate_id, to_stage, at) VALUES (?, 'applied', ?)", (cid, at))
        return self.get(cid)

    def move(self, candidate_id: int, to: Stage, note: str = "") -> Candidate:
        to, at = Stage(to), to_text(self.now())
        with self._write() as db:
            current = self._load(db, candidate_id)
            check_move(current.stage, to)
            db.execute(
                "INSERT INTO events (candidate_id, from_stage, to_stage, note, at) VALUES (?, ?, ?, ?, ?)",
                (candidate_id, current.stage.value, to.value, note, at),
            )
        return self.get(candidate_id)

    def get(self, candidate_id: int) -> Candidate:
        with closing(self._connect()) as db:
            return self._load(db, candidate_id)

    def all(self) -> list[Candidate]:
        with closing(self._connect()) as db:
            people = db.execute("SELECT * FROM candidates ORDER BY id").fetchall()
            events = db.execute("SELECT * FROM events ORDER BY candidate_id, id").fetchall()
        by_person: dict[int, list[sqlite3.Row]] = {}
        for row in events:
            by_person.setdefault(row["candidate_id"], []).append(row)
        return [_build(p, by_person.get(p["id"], [])) for p in people]

    def _load(self, db: sqlite3.Connection, candidate_id: int) -> Candidate:
        person = db.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
        if person is None:
            raise NotFound(f"No candidate with id {candidate_id}.")
        return _build(person, db.execute("SELECT * FROM events WHERE candidate_id = ? ORDER BY id", (candidate_id,)).fetchall())


def _build(person: sqlite3.Row, rows: list[sqlite3.Row]) -> Candidate:
    events = tuple(
        Event(Stage(r["from_stage"]) if r["from_stage"] else None, Stage(r["to_stage"]), r["note"], from_text(r["at"]))
        for r in rows
    )
    return Candidate(person["id"], person["name"], events)
