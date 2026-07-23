"""FastAPI router — research-backed situation intel for players."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.config import MY_ROSTER_ID
from sleeper_ffm.model.context_table import load_context_table
from sleeper_ffm.model.player_intel import build_roster_intel
from sleeper_ffm.model.research.archetypes import build as build_archetypes
from sleeper_ffm.model.research.qb_quality import team_qb_context
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

router = APIRouter(prefix="/intel", tags=["intel"])
_ROSTER_QUERY = Query(default=None, description="Scope to one roster; omit to scan the league")


@router.get("/players")
def player_intel(roster_id: int | None = _ROSTER_QUERY) -> dict:
    """Return situation flags (studies S2-S6) for a roster, or the whole league.

    Args:
        roster_id: Sleeper roster to scope to. Omit for a league-wide sweep, which
            is what waiver and trade-target scans want.
    """
    try:
        context = load_context_table()
        if context.is_empty():
            raise HTTPException(
                status_code=503, detail="context table not built — run `sffm ingest`"
            )

        held: set[str] | None = None
        if roster_id is not None:
            with SleeperClient() as client:
                rosters = client.rosters()
            mine = next((r for r in rosters if r.roster_id == roster_id), None)
            if mine is None:
                raise HTTPException(status_code=404, detail=f"roster {roster_id} not found")
            held = {str(p) for p in mine.players}

        try:
            latest = context["season"].max()
            archetypes = (
                build_archetypes([int(latest)]) if isinstance(latest, (int, float)) else None
            )
        except Exception as exc:
            log.warning("intel: archetypes unavailable, attrition flags omitted: %s", exc)
            archetypes = None

        try:
            qb_context = team_qb_context(int(latest)) if isinstance(latest, (int, float)) else {}
        except Exception as exc:
            log.warning("intel: QB context unavailable (%s)", exc)
            qb_context = {}

        intel = build_roster_intel(
            context, archetypes=archetypes, sleeper_ids=held, qb_context=qb_context
        )
        return {
            "roster_id": roster_id if roster_id is not None else MY_ROSTER_ID,
            "scope": "roster" if held is not None else "league",
            "players": [dataclasses.asdict(record) for record in intel],
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("player intel failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
