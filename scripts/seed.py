"""Fills a database with a small hiring pipeline, backdated from now.

    python scripts/seed.py --reset

Priya Sharma, Priyanka Shah, Rahul Sharma and Sharan Iyer are there to make typo ranking visible.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.stages import Stage  # noqa: E402
from pipeline.store import Store, utcnow  # noqa: E402

# (days ago, stage, note) in the order things happened
PEOPLE = {
    "Neha Kapoor": [(1.5, "applied", "")],
    "Zoya Ahmed": [(0.3, "applied", "")],
    "Priya Sharma": [(12, "applied", ""), (9.2, "screening", "Recruiter call booked, waiting on her availability.")],
    "Priyanka Shah": [(6, "applied", ""), (2, "screening", "")],
    "Rahul Sharma": [(10, "applied", ""), (8.5, "screening", "")],
    "Aarav Mehta": [(14, "applied", ""), (12, "screening", ""), (1, "interview", "Panel set for Friday.")],
    "Sharan Iyer": [(9, "applied", ""), (6, "screening", ""), (2.5, "interview", "")],
    "Vikram Singh": [(20, "applied", ""), (17, "screening", ""), (11, "interview", "Second round pending feedback.")],
    "Karan Malhotra": [(7, "applied", ""), (4.6, "screening", ""), (0.4, "interview", "")],
    "Arjun Reddy": [(16, "applied", ""), (14, "screening", ""), (9, "interview", ""), (5, "offer", "Offer sent, awaiting a reply.")],
    "Kabir Anand": [(19, "applied", ""), (16, "screening", ""), (11, "interview", ""), (7, "offer", ""), (4, "rejected", "Offer declined over compensation.")],
    "Tara Bose": [(24, "applied", ""), (21, "screening", ""), (17, "interview", ""), (12, "offer", ""), (9, "rejected", "Offer withdrawn after the reference check.")],
    "Siddharth Rao": [(22, "applied", ""), (20, "screening", ""), (15, "interview", ""), (10, "offer", ""), (6, "hired", "Accepted. Joining in November.")],
    "Lakshmi Pillai": [(18, "applied", ""), (16, "screening", ""), (11, "interview", ""), (6, "offer", ""), (2, "hired", "")],
    "Sana Khan": [(12, "applied", ""), (10, "screening", ""), (6, "interview", ""), (2, "rejected", "Weak on system design.")],
    "Devansh Verma": [(8, "applied", ""), (3, "rejected", "Missing the required experience.")],
}


def build(db_path: str, now: datetime | None = None) -> Store:
    now = now or utcnow()
    clock = {"at": now}
    store = Store(db_path, now=lambda: clock["at"])
    for name, timeline in PEOPLE.items():
        clock["at"] = now - timedelta(days=timeline[0][0])
        person = store.add_candidate(name)
        for days, stage, note in timeline[1:]:
            clock["at"] = now - timedelta(days=days)
            store.move(person.id, Stage(stage), note)
    return store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=os.environ.get("PIPELINE_DB", "pipeline.db"))
    parser.add_argument("--reset", action="store_true", help="delete the database first")
    args = parser.parse_args()
    if args.reset:
        for suffix in ("", "-wal", "-shm"):
            Path(args.db + suffix).unlink(missing_ok=True)
    elif Path(args.db).exists() and Store(args.db).all():
        sys.exit(f"{args.db} already has candidates. Run with --reset to start over.")
    print(f"Seeded {len(build(args.db).all())} candidates into {args.db}")


if __name__ == "__main__":
    main()
