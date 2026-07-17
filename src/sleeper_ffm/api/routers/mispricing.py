"""FastAPI router — league-specific mispricing leaderboard."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.model.mispricing import build_mispricing

log = logging.getLogger(__name__)

router = APIRouter(prefix="/mispricing", tags=["mispricing"])

_SEASONS_QUERY = Query(default=None)
_TOP_QUERY = Query(default=15, ge=1, le=100)
_MIN_GAMES_QUERY = Query(default=6, ge=1, le=17)


@router.get("")
def mispricing(
    seasons: list[int] | None = _SEASONS_QUERY,
    top: int = _TOP_QUERY,
    min_games: int = _MIN_GAMES_QUERY,
) -> dict:
    """Return the scoring-leverage mispricing board (buy/sell vs the generic market)."""
    try:
        board = build_mispricing(seasons=seasons, min_games=min_games, top=top)
        result = dataclasses.asdict(board)
        result["data_quality"] = "DEGRADED" if board.warnings else "FULL"
        return result
    except Exception as exc:
        log.exception("mispricing board failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
