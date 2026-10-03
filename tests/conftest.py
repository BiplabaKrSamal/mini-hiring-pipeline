from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from pipeline.api import create_app
from pipeline.store import Store

# Thursday 1 Oct 2026, 00:09 in Agra. Just past midnight on purpose: the UTC date and the
# local date differ, which is where time-zone bugs live.
NOW = datetime(2026, 9, 30, 18, 39, tzinfo=timezone.utc)


class Clock:
    """A clock the test controls."""

    def __init__(self):
        self.at = NOW

    def __call__(self):
        return self.at

    def advance(self, **delta):
        self.at += timedelta(**delta)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    return Store(str(tmp_path / "test.db"), now=clock)


@pytest.fixture
def client(tmp_path, clock):
    return TestClient(create_app(str(tmp_path / "test.db"), now=clock))
