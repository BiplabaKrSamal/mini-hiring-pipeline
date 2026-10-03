"""The pipeline's rules. No I/O."""
from __future__ import annotations

from enum import Enum

from .errors import Conflict


class Stage(str, Enum):
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"

    @property
    def label(self) -> str:
        return self.value.capitalize()

    @property
    def is_final(self) -> bool:
        return self in FINAL


PIPELINE = (Stage.APPLIED, Stage.SCREENING, Stage.INTERVIEW, Stage.OFFER, Stage.HIRED)
FINAL = frozenset({Stage.HIRED, Stage.REJECTED})
BOARD_ORDER = PIPELINE + (Stage.REJECTED,)


def allowed_moves(stage: Stage) -> tuple[Stage, ...]:
    """The next stage, or rejection. Nothing once a final outcome is reached."""
    if stage in FINAL:
        return ()
    return (PIPELINE[PIPELINE.index(stage) + 1], Stage.REJECTED)


def check_move(current: Stage, target: Stage) -> None:
    allowed = allowed_moves(current)
    if target in allowed:
        return
    if current in FINAL:
        raise Conflict(f"{current.label} is a final outcome and can't be changed.")
    if target == current:
        raise Conflict(f"Already in {current.label}.")
    if target in PIPELINE and PIPELINE.index(target) < PIPELINE.index(current):
        raise Conflict(f"Can't move back from {current.label} to {target.label}.")
    raise Conflict(f"Can't skip from {current.label} to {target.label}. The next stage is {allowed[0].label}.")
