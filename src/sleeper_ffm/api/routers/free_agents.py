"""FastAPI router — projection-ranked free-agent board."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.model.free_agents import build_free_agent_board

log = logging.getLogger(__name__)

router = APIRouter(prefix="/free-agents", tags=["free-agents"])

_POS_QUERY = Query(default=None)
_TOP_QUERY = Query(default=12, ge=1, le=50)


@router.get("")
def free_agents(position: str | None = _POS_QUERY, top: int = _TOP_QUERY) -> dict:
    """Return the best available players by projected value (optionally one position)."""
    try:
        board = build_free_agent_board(top_n=top)
        payload = dataclasses.asdict(board)
        if position:
            pos = position.upper()
            payload["overall"] = payload["by_position"].get(pos, [])
        return payload
    except Exception as exc:
        log.exception("free-agent board failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
