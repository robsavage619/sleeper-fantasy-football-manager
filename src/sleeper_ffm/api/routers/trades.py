"""FastAPI router — trade analysis and owned pick inventory."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sleeper_ffm.config import MY_ROSTER_ID

log = logging.getLogger(__name__)

router = APIRouter(prefix="/trades", tags=["trades"])


class TradeAnalysisRequest(BaseModel):
    """Request body for POST /trades/analyze."""

    give_player_ids: list[str] = []
    get_player_ids: list[str] = []
    give_pick_ids: list[str] = []
    get_pick_ids: list[str] = []
    seasons: list[int] | None = None


@router.post("/analyze")
def analyze_trade(req: TradeAnalysisRequest) -> dict:
    """Score both sides of a trade and return dynasty values + Claude Code prompt.

    Returns give_value, get_value, delta, verdict (ACCEPT/CLOSE/DECLINE), and
    a structured prompt ready to paste into Claude Code for deeper reasoning.
    """
    from sleeper_ffm.model.dynasty import value_player
    from sleeper_ffm.model.valuation import build_player_assets
    from sleeper_ffm.prompts.trade import build_trade_prompt, value_trade_pick

    seasons = req.seasons or [2024]
    all_ids = set(req.give_player_ids) | set(req.get_player_ids)

    if all_ids:
        try:
            assets = build_player_assets(seasons=seasons)
        except Exception as exc:
            log.exception("failed to build player assets for trade analysis")
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        asset_map = {p.player_id: p for p in assets}
    else:
        asset_map = {}

    give_players = [asset_map[pid] for pid in req.give_player_ids if pid in asset_map]
    get_players = [asset_map[pid] for pid in req.get_player_ids if pid in asset_map]

    give_value = (
        sum(value_player(p) for p in give_players)
        + sum(value_trade_pick(pid) for pid in req.give_pick_ids)
    )
    get_value = (
        sum(value_player(p) for p in get_players)
        + sum(value_trade_pick(pid) for pid in req.get_pick_ids)
    )
    delta = get_value - give_value
    verdict = "ACCEPT" if delta > 10 else "DECLINE" if delta < -10 else "CLOSE"

    prompt = build_trade_prompt(
        give_player_ids=req.give_player_ids,
        get_player_ids=req.get_player_ids,
        give_pick_ids=req.give_pick_ids,
        get_pick_ids=req.get_pick_ids,
        seasons=seasons,
    )

    return {
        "give_value": round(give_value, 2),
        "get_value": round(get_value, 2),
        "delta": round(delta, 2),
        "verdict": verdict,
        "prompt": prompt,
    }


@router.get("/picks")
def my_traded_picks() -> list[dict]:
    """Return traded picks currently held by Rob's roster (roster_id == MY_ROSTER_ID)."""
    from sleeper_ffm.sleeper.client import SleeperClient

    with SleeperClient() as c:
        all_picks = c.traded_picks()

    return [p.model_dump() for p in all_picks if p.roster_id == MY_ROSTER_ID]
