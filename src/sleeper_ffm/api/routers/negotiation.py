"""FastAPI router — trade negotiation copilot."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.prompts.negotiation import build_negotiation_brief

log = logging.getLogger(__name__)

router = APIRouter(prefix="/negotiation", tags=["negotiation"])

_PLAYER_QUERY = Query(...)
_OWNER_QUERY = Query(...)


@router.get("")
def negotiation(player_id: str = _PLAYER_QUERY, owner_roster_id: int = _OWNER_QUERY) -> dict:
    """Return a negotiation brief for acquiring a player from a given owner."""
    try:
        return dataclasses.asdict(build_negotiation_brief(player_id, owner_roster_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("negotiation brief failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
