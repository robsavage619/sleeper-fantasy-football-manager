"""FastAPI router — the GM's weekly address prompt."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from sleeper_ffm.prompts.gm_address import gather_gm_address

log = logging.getLogger(__name__)

router = APIRouter(prefix="/gm-address", tags=["gm-address"])


@router.get("")
def gm_address() -> dict:
    """Return the weekly-address prompt for Claude Code to write the column."""
    try:
        stamp = datetime.now(UTC).isoformat()
        return {"prompt": gather_gm_address(generated_at=stamp), "generated_at": stamp}
    except Exception as exc:
        log.exception("gm address failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
