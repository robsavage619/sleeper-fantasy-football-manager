"""FastAPI router — FAAB clearing-price model (position percentiles, owner profiles)."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException

from sleeper_ffm.model.faab_market import build_faab_market

log = logging.getLogger(__name__)

router = APIRouter(prefix="/faab-market", tags=["faab-market"])


@router.get("")
def faab_market() -> dict:
    """Return this league's winning-bid percentiles by position and owner bid profiles."""
    try:
        market = build_faab_market()
        return {
            "seasons_covered": market.seasons_covered,
            "n_bids": len(market.bids),
            "by_position": {k: dataclasses.asdict(v) for k, v in market.by_position.items()},
            "by_owner": {k: dataclasses.asdict(v) for k, v in market.by_owner.items()},
            "warnings": market.warnings,
        }
    except Exception as exc:
        log.exception("faab market failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
