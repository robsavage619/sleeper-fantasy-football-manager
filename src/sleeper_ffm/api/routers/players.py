"""FastAPI router - player intelligence profiles."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.model.player_profile import build_player_profile

log = logging.getLogger(__name__)

router = APIRouter(prefix="/players", tags=["players"])
_SEASONS_QUERY = Query(default=None)


@router.get("/{player_id}/profile")
def player_profile(
    player_id: str,
    seasons: list[int] | None = _SEASONS_QUERY,
) -> dict:
    """Return historical stats, usage, injuries, and valuation for one player."""
    try:
        return dataclasses.asdict(build_player_profile(player_id=player_id, seasons=seasons))
    except Exception as exc:
        log.exception("player profile failed: %s", player_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
