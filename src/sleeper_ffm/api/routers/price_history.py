"""FastAPI router — FantasyCalc price-history momentum and mean-reversion signals."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.market.price_history import load_price_history, player_price_trend, top_movers

log = logging.getLogger(__name__)

router = APIRouter(prefix="/market/price-history", tags=["price-history"])

_LIMIT_QUERY = Query(default=25, ge=1, le=200)
_DIRECTION_QUERY = Query(default="up", pattern="^(up|down)$")


@router.get("/movers")
def movers(direction: str = _DIRECTION_QUERY, limit: int = _LIMIT_QUERY) -> dict:
    """Return the biggest price risers or fallers across all archived snapshots."""
    try:
        index = load_price_history()
        trends = top_movers(direction=direction, limit=limit, index=index)
        return {
            "snapshot_dates": index.snapshot_dates,
            "direction": direction,
            "movers": [dataclasses.asdict(t) for t in trends],
            "warnings": index.warnings,
            "data_quality": "DEGRADED" if index.warnings else "FULL",
        }
    except Exception as exc:
        log.exception("price history movers failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{sleeper_id}")
def player_trend(sleeper_id: str) -> dict:
    """Return one player's price momentum and mean-reversion z-score."""
    try:
        index = load_price_history()
        trend = player_price_trend(sleeper_id, index)
        return {
            "snapshot_dates": index.snapshot_dates,
            **dataclasses.asdict(trend),
            "warnings": index.warnings,
            "data_quality": "DEGRADED" if index.warnings else "FULL",
        }
    except Exception as exc:
        log.exception("price history trend failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
