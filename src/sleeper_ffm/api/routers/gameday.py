"""FastAPI router — live gameday co-pilot."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.model.gameday import build_gameday

log = logging.getLogger(__name__)

router = APIRouter(prefix="/gameday", tags=["gameday"])

_WEEK_QUERY = Query(default=1, ge=1, le=18)


@router.get("")
def gameday(week: int = _WEEK_QUERY) -> dict:
    """Return this week's matchup win probability and pre-lock lineup edge."""
    try:
        return dataclasses.asdict(build_gameday(week))
    except Exception as exc:
        log.exception("gameday brief failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
