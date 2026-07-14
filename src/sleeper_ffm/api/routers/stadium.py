"""FastAPI router — stadium & weather performance splits."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException

from sleeper_ffm.model.stadium_weather import build_environment_splits

log = logging.getLogger(__name__)

router = APIRouter(prefix="/environment", tags=["stadium-weather"])


@router.get("")
def environment_flags() -> dict:
    """Return players with a material stadium/weather lean (the start/sit-relevant ones)."""
    try:
        profiles = build_environment_splits()
        flagged = [
            dataclasses.asdict(p) for p in profiles.values() if p.flags and p.total_games >= 6
        ]
        flagged.sort(key=lambda p: len(p["flags"]), reverse=True)
        return {"count": len(profiles), "flagged": flagged}
    except Exception as exc:
        log.exception("environment flags failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{player_id}")
def player_environment(player_id: str) -> dict:
    """Return one player's full stadium/weather split profile."""
    try:
        profile = build_environment_splits().get(player_id)
        if profile is None:
            raise HTTPException(status_code=404, detail=f"No environment data for {player_id}")
        return dataclasses.asdict(profile)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("player environment failed: %s", player_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
