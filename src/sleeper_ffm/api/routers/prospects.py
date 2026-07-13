"""FastAPI router — CFBD dynasty prospect scouting board."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException

log = logging.getLogger(__name__)

router = APIRouter(prefix="/draft", tags=["draft"])


@router.get("/prospects")
def draft_prospects(year: int = 2025, top: int = 50) -> list[dict]:
    """Return top dynasty prospects scored from CFBD college data.

    Args:
        year: Draft class year (2025 or 2026).
        top: Number of prospects to return (default 50).
    """
    from sleeper_ffm.cfbd.loader import load_prospects

    try:
        profiles = load_prospects(year=year, top=top)
    except Exception as exc:
        log.exception("load_prospects failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return [dataclasses.asdict(p) for p in profiles]
