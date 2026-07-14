"""FastAPI router — real-world intelligence feed (injuries, depth, league moves)."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException

from sleeper_ffm.config import MY_ROSTER_ID

log = logging.getLogger(__name__)

router = APIRouter(prefix="/intel", tags=["intel"])


@router.get("/feed")
def intel_feed(roster_id: int = MY_ROSTER_ID) -> dict:
    """Aggregated injuries, depth-chart flags, opportunity signals, and league moves."""
    from sleeper_ffm.model.news_feed import build_feed

    try:
        return dataclasses.asdict(build_feed(roster_id))
    except Exception as exc:
        log.exception("intel feed failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
