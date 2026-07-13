"""FastAPI router — multi-season league transaction history."""

from __future__ import annotations

import dataclasses
import json
import logging
import time

from fastapi import APIRouter, Query

from sleeper_ffm.config import CACHE_DIR
from sleeper_ffm.model.owner_history import build_league_history

router = APIRouter(prefix="/owners", tags=["owners"])
log = logging.getLogger(__name__)

_HISTORY_CACHE = CACHE_DIR / "history.json"
_HISTORY_TTL = 3600  # 1 hour


@router.get("/history")
def league_history(refresh: bool = Query(default=False)) -> dict:
    """Return multi-season transaction history for every current owner.

    Result is cached to disk for 1 hour. Pass ?refresh=true to force recompute.
    """
    if (
        not refresh
        and _HISTORY_CACHE.exists()
        and (time.time() - _HISTORY_CACHE.stat().st_mtime) < _HISTORY_TTL
    ):
        log.info("history: returning cached result from %s", _HISTORY_CACHE)
        return json.loads(_HISTORY_CACHE.read_text())

    log.info("history: cache miss — rebuilding (refresh=%s)", refresh)
    result = dataclasses.asdict(build_league_history())
    _HISTORY_CACHE.write_text(json.dumps(result))
    log.info("history: cached to %s", _HISTORY_CACHE)
    return result
