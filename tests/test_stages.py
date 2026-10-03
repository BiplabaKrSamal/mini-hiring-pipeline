import pytest

from pipeline.errors import Conflict
from pipeline.stages import Stage, allowed_moves, check_move

S = Stage
LEGAL = {
    S.APPLIED: {S.SCREENING, S.REJECTED},
    S.SCREENING: {S.INTERVIEW, S.REJECTED},
    S.INTERVIEW: {S.OFFER, S.REJECTED},
    S.OFFER: {S.HIRED, S.REJECTED},
    S.HIRED: set(),
    S.REJECTED: set(),
}


@pytest.mark.parametrize("current", Stage)
@pytest.mark.parametrize("target", Stage)
def test_only_the_next_stage_or_rejection_is_allowed(current, target):
    assert set(allowed_moves(current)) == LEGAL[current]
    if target in LEGAL[current]:
        check_move(current, target)
    else:
        with pytest.raises(Conflict):
            check_move(current, target)


@pytest.mark.parametrize("current, target, words", [
    (S.APPLIED, S.OFFER, "skip"),
    (S.INTERVIEW, S.APPLIED, "back"),
    (S.SCREENING, S.SCREENING, "Already"),
    (S.HIRED, S.INTERVIEW, "final"),
    (S.REJECTED, S.SCREENING, "final"),
])
def test_the_message_says_what_went_wrong(current, target, words):
    with pytest.raises(Conflict, match=words):
        check_move(current, target)
