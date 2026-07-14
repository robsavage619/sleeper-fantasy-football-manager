"""FastAPI router — Monte-Carlo season / title-equity simulation."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.model.season_sim import build_season_sim

log = logging.getLogger(__name__)

router = APIRouter(prefix="/season-sim", tags=["season-sim"])

_SIMS_QUERY = Query(default=4000, ge=200, le=50000)


@router.get("")
def season_sim(n_sims: int = _SIMS_QUERY) -> dict:
    """Return per-team playoff/title odds from a Monte-Carlo season simulation."""
    try:
        return dataclasses.asdict(build_season_sim(n_sims=n_sims))
    except Exception as exc:
        log.exception("season sim failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
