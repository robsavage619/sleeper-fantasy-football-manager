"""FastAPI router — handcuff & leverage map."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException

from sleeper_ffm.model.handcuff import build_handcuff_map

log = logging.getLogger(__name__)

router = APIRouter(prefix="/handcuffs", tags=["handcuff"])


@router.get("")
def handcuffs() -> dict:
    """Return my roster's contingent-value picture plus league leverage stashes."""
    try:
        return dataclasses.asdict(build_handcuff_map())
    except Exception as exc:
        log.exception("handcuff map failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
