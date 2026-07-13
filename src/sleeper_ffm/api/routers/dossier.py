"""FastAPI router — rich per-owner dossier."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.model.owner_dossier import build_dossier

router = APIRouter(prefix="/owners", tags=["owners"])
log = logging.getLogger(__name__)


@router.get("/dossier/{roster_id}")
def owner_dossier(roster_id: int, season: int = Query(default=2024)) -> dict:
    """Return the full dossier for one roster (players, breakdowns, contention, picks)."""
    try:
        return dataclasses.asdict(build_dossier(roster_id, season))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
