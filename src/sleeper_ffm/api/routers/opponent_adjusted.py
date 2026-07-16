"""FastAPI router — opponent-adjusted (schedule-neutral) production board."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.model.opponent_adjusted import build_opponent_adjusted

log = logging.getLogger(__name__)

router = APIRouter(prefix="/opponent-adjusted", tags=["opponent-adjusted"])

_TOP_QUERY = Query(default=15, ge=1, le=100)
_SEASON_QUERY = Query(default=None)


@router.get("")
def opponent_adjusted(season: int | None = _SEASON_QUERY, top: int = _TOP_QUERY) -> dict:
    """Return players whose raw FP was most inflated/deflated by schedule strength."""
    try:
        return dataclasses.asdict(build_opponent_adjusted(season=season, top=top))
    except Exception as exc:
        log.exception("opponent-adjusted board failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
