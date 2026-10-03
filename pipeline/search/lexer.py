"""Splits the search box text into tokens."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .fuzzy import fold


@dataclass(frozen=True)
class Tok:
    kind: str   # word | num | iso | comma
    text: str   # lowercase, no accents or apostrophes
    raw: str    # as typed, for messages


_TOKEN = re.compile(r"(?P<iso>\d{4}-\d{2}-\d{2})|(?P<num>\d+)|(?P<word>[^\W\d_]+(?:['’][^\W\d_]+)*)|(?P<comma>,)")


def tokenize(text: str) -> list[Tok]:
    return [Tok(m.lastgroup, fold(m.group()), m.group()) for m in _TOKEN.finditer(text)]
