"""FastAPI router — league contention windows (buyer/seller classifier)."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException

from sleeper_ffm.model.contention import build_contention

log = logging.getLogger(__name__)

router = APIRouter(prefix="/contention", tags=["contention"])


@router.get("")
def contention() -> dict:
    """Return every roster's contention window with buy/sell guidance."""
    try:
        board = build_contention()
        result = dataclasses.asdict(board)
        result["data_quality"] = "DEGRADED" if board.warnings else "FULL"
        return result
    except Exception as exc:
        log.exception("contention board failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
