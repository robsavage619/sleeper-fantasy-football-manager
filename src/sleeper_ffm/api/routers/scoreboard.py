"""FastAPI router — recommendation scoreboard (the GM's track record)."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException

from sleeper_ffm.model.rec_scoreboard import build_scoreboard

log = logging.getLogger(__name__)

router = APIRouter(prefix="/scoreboard", tags=["scoreboard"])


@router.get("")
def scoreboard() -> dict:
    """Return the GM's recommendation track record (graded where ground truth exists)."""
    try:
        return dataclasses.asdict(build_scoreboard())
    except Exception as exc:
        log.exception("scoreboard failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
