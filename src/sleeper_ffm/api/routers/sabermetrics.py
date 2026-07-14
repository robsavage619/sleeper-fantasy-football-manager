"""FastAPI routers — in-house player and GM sabermetrics."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.model.gm_metrics import build_gm_metrics
from sleeper_ffm.model.sabermetrics import build_player_sabermetrics

log = logging.getLogger(__name__)

players_router = APIRouter(prefix="/players", tags=["sabermetrics"])
owners_router = APIRouter(prefix="/owners", tags=["sabermetrics"])

_SEASONS_QUERY = Query(default=None)


@players_router.get("/{player_id}/sabermetrics")
def player_sabermetrics(
    player_id: str,
    seasons: list[int] | None = _SEASONS_QUERY,
) -> dict:
    """Return the full in-house sabermetric suite for one player under this league's scoring."""
    try:
        return dataclasses.asdict(
            build_player_sabermetrics(player_id=player_id, seasons=seasons)
        )
    except Exception as exc:
        log.exception("player sabermetrics failed: %s", player_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@owners_router.get("/sabermetrics")
def owners_sabermetrics() -> list[dict]:
    """Return the GM sabermetric suite (luck, lineup efficiency, FAAB, trade ledger) per owner."""
    try:
        return [dataclasses.asdict(r) for r in build_gm_metrics()]
    except Exception as exc:
        log.exception("owner sabermetrics failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
