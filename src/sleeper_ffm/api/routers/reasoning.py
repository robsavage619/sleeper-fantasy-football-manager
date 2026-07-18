"""FastAPI router — focused agent-reasoning prompt surfaces.

Each endpoint mirrors ``GET /ai/briefing``: it returns ``{prompt, schema}`` for one
decision surface that otherwise terminates at raw numbers. An agent (Claude Code)
reasons over the prompt and posts a typed finding back via ``POST /findings/typed``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from sleeper_ffm.config import MY_ROSTER_ID
from sleeper_ffm.prompts import surfaces

log = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/dossier/{roster_id}")
def ai_dossier(roster_id: int) -> dict[str, Any]:
    """Reasoning prompt: how to win trades against one specific manager."""
    return {"prompt": surfaces.build_dossier_prompt(roster_id), "schema": surfaces.DOSSIER_SCHEMA}


@router.get("/market-edges")
def ai_market_edges() -> dict[str, Any]:
    """Reasoning prompt: reconcile mispricing + regression + opponent-adjusted into buy/sell."""
    return {"prompt": surfaces.build_market_edges_prompt(), "schema": surfaces.MARKET_EDGE_SCHEMA}


@router.get("/waivers")
def ai_waivers() -> dict[str, Any]:
    """Reasoning prompt: a FAAB bid plan over trending adds + snap-share risers."""
    return {"prompt": surfaces.build_waiver_plan_prompt(), "schema": surfaces.WAIVER_PLAN_SCHEMA}


@router.get("/trade-plan")
def ai_trade_plan(_my_roster_id: int = MY_ROSTER_ID) -> dict[str, Any]:
    """Reasoning prompt: franchise buy/sell posture + sequenced trade plan."""
    return {"prompt": surfaces.build_trade_plan_prompt(), "schema": surfaces.TRADE_PLAN_SCHEMA}
