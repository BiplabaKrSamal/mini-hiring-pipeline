"""Vercel entrypoint.

Vercel's filesystem is read-only except /tmp, and /tmp is wiped whenever an instance is
replaced. So this deployment is a demo: it starts from the seed data, and changes made on
the page last until the instance restarts. To keep history, run `python -m pipeline` on a
host with a persistent disk.
"""
import os
from pathlib import Path

from pipeline.api import create_app
from scripts.seed import build

DB = os.environ.get("PIPELINE_DB", "/tmp/pipeline.db")
if not Path(DB).exists():
    build(DB)

app = create_app(DB, demo=True)
