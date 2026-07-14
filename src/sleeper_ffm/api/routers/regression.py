"""FastAPI router — TD-regression buy-low / sell-high board."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.model.regression import build_regression

log = logging.getLogger(__name__)

router = APIRouter(prefix="/regression", tags=["regression"])

_TOP_QUERY = Query(default=15, ge=1, le=100)


@router.get("")
def regression(top: int = _TOP_QUERY) -> dict:
    """Return TD-over-expected regression candidates (sell-high and buy-low)."""
    try:
        return dataclasses.asdict(build_regression(top=top))
    except Exception as exc:
        log.exception("regression board failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
