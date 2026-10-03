"""HTTP layer. The rules live in stages.py, store.py and search/."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import search
from .errors import PipelineError
from .search.parser import STUCK_AFTER
from .stages import BOARD_ORDER, Stage, allowed_moves
from .store import Candidate, Clock, Store, to_text, utcnow

WEB = Path(__file__).resolve().parent.parent / "web"


class NewCandidate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)


class NewMove(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    to: Stage
    note: str = Field("", max_length=500)


def summary(c: Candidate, now: datetime) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "stage": c.stage.value,
        "stage_since": to_text(c.stage_since),
        "in_stage_seconds": max(0, int((now - c.stage_since).total_seconds())),
        "is_final": c.stage.is_final,
        "next": [s.value for s in allowed_moves(c.stage)],
    }


def detail(c: Candidate, now: datetime) -> dict:
    history = []
    for i, e in enumerate(c.events):
        until = c.events[i + 1].at if i + 1 < len(c.events) else now
        history.append({
            "from": e.from_stage.value if e.from_stage else None,
            "to": e.to_stage.value,
            "note": e.note,
            "at": to_text(e.at),
            "seconds_in_stage": max(0, int((until - e.at).total_seconds())),
        })
    return {**summary(c, now), "history": history}


def create_app(db_path: str | None = None, now: Clock = utcnow, demo: bool = False) -> FastAPI:
    store = Store(db_path or os.environ.get("PIPELINE_DB", "pipeline.db"), now)
    app = FastAPI(title="Mini Hiring Pipeline")

    @app.exception_handler(PipelineError)
    async def pipeline_error(_: Request, err: PipelineError):
        return JSONResponse({"error": str(err)}, status_code=err.status)

    @app.exception_handler(RequestValidationError)
    async def bad_request(_: Request, err: RequestValidationError):
        first = err.errors()[0]
        field = ".".join(str(p) for p in first["loc"] if p not in ("body", "query"))
        return JSONResponse({"error": f"{field}: {first['msg']}" if field else first["msg"]}, status_code=422)

    @app.get("/api/candidates")
    def list_candidates():
        at = store.now()
        return {
            "demo": demo,
            "stuck_after_seconds": STUCK_AFTER,
            "stages": [{"id": s.value, "label": s.label} for s in BOARD_ORDER],
            "candidates": [summary(c, at) for c in store.all()],
        }

    @app.post("/api/candidates", status_code=201)
    def add_candidate(body: NewCandidate):
        return detail(store.add_candidate(body.name), store.now())

    @app.get("/api/candidates/{candidate_id}")
    def get_candidate(candidate_id: int):
        return detail(store.get(candidate_id), store.now())

    @app.post("/api/candidates/{candidate_id}/moves")
    def move_candidate(candidate_id: int, body: NewMove):
        return detail(store.move(candidate_id, body.to, body.note), store.now())

    @app.get("/api/search")
    def search_candidates(q: str = Query("", max_length=300), tz: str = "UTC"):
        at = store.now()
        found = search.run(q, store.all(), at, tz)
        return {
            "query": found.query,
            "mode": found.mode,
            "order": found.order,
            "interpretation": found.interpretation,
            "notices": [{"level": n.level, "message": n.message} for n in found.notices],
            "results": [{**summary(h.candidate, at), "reasons": h.reasons} for h in found.hits],
            "empty_reason": found.empty_reason,
        }

    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    return app
