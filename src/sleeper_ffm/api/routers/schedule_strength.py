"""FastAPI router — defense-vs-position and strength of schedule."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.model.schedule_strength import build_schedule_strength

log = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule-strength", tags=["schedule-strength"])

_POS_QUERY = Query(default=None)


@router.get("")
def schedule_strength(position: str | None = _POS_QUERY) -> dict:
    """Return DvP indices plus full-season and playoff SoS (optionally one position)."""
    try:
        ss = build_schedule_strength()
        payload = dataclasses.asdict(ss)
        if position:
            pos = position.upper()
            payload["sos"] = [s for s in payload["sos"] if s["position"] == pos]
        return payload
    except Exception as exc:
        log.exception("schedule strength failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
