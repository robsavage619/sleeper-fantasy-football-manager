"""FastAPI router — wire early-warning (snap-share risers)."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.model.wire_watch import build_wire_watch

log = logging.getLogger(__name__)

router = APIRouter(prefix="/wire-watch", tags=["wire-watch"])

_AVAILABLE_QUERY = Query(default=True)


@router.get("")
def wire_watch(available_only: bool = _AVAILABLE_QUERY) -> dict:
    """Return snap-share risers; by default only those available in this league."""
    try:
        watch = build_wire_watch()
        payload = dataclasses.asdict(watch)
        if available_only:
            payload["alerts"] = [a for a in payload["alerts"] if a["available"]]
        return payload
    except Exception as exc:
        log.exception("wire watch failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
