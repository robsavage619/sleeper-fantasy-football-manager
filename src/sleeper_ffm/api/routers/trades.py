"""FastAPI router — trade analysis and owned pick inventory."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from sleeper_ffm.config import DEFAULT_VALUE_SEASON, MY_ROSTER_ID, PREFERRED_VALUE_SEASON
from sleeper_ffm.model.dynasty import PlayerAsset

log = logging.getLogger(__name__)

router = APIRouter(prefix="/trades", tags=["trades"])


class TradeAnalysisRequest(BaseModel):
    """Request body for POST /trades/analyze."""

    give_player_ids: list[str] = []
    get_player_ids: list[str] = []
    give_pick_ids: list[str] = []
    get_pick_ids: list[str] = []
    seasons: list[int] | None = None


def _rookie_asset_from_sleeper(pid: str, sleeper_players: dict[str, dict]) -> PlayerAsset | None:
    """Build a conservative fallback asset for a Sleeper-ranked young player."""
    from sleeper_ffm.model.valuation import SKILL_POSITIONS, _rookie_fpar

    player = sleeper_players.get(pid)
    if not player:
        return None

    pos = player.get("position", "")
    search_rank = player.get("search_rank")
    years_exp = player.get("years_exp")
    if pos not in SKILL_POSITIONS or search_rank is None or years_exp is None or years_exp > 1:
        return None

    return PlayerAsset(
        player_id=pid,
        name=player.get("full_name") or player.get("search_full_name") or f"Player {pid}",
        position=pos,
        age=float(player.get("age") or 22),
        current_fpar=_rookie_fpar(int(search_rank)),
        team=player.get("team") or "",
        is_taxi=True,
    )


def _http_400(detail: dict) -> HTTPException:
    """Return a typed 400 exception with structured detail."""
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.post("/analyze")
def analyze_trade(req: TradeAnalysisRequest) -> dict:
    """Score both sides of a trade and return dynasty values + Claude Code prompt.

    Returns give_value, get_value, delta, verdict (ACCEPT/CLOSE/DECLINE), and
    a structured prompt ready to paste into Claude Code for deeper reasoning.
    """
    from sleeper_ffm.model.dynasty import value_player
    from sleeper_ffm.model.valuation import build_player_assets
    from sleeper_ffm.prompts.trade import (
        build_trade_prompt,
        validate_trade_pick_ids,
        value_trade_pick,
    )
    from sleeper_ffm.sleeper.client import SleeperClient

    if not (req.give_player_ids or req.give_pick_ids) or not (
        req.get_player_ids or req.get_pick_ids
    ):
        raise _http_400(
            {
                "error": "trade_must_have_assets_on_both_sides",
                "message": "Trade analysis requires at least one GIVE asset and one GET asset.",
            }
        )

    invalid_pick_ids = validate_trade_pick_ids(req.give_pick_ids + req.get_pick_ids)
    if invalid_pick_ids:
        raise _http_400(
            {
                "error": "invalid_pick_ids",
                "invalid_pick_ids": invalid_pick_ids,
                "message": "Pick IDs must look like 2026_R2, 2026_2, or 2026_2_6.",
            }
        )

    seasons = req.seasons or [DEFAULT_VALUE_SEASON]
    warnings = []
    if req.seasons is None and DEFAULT_VALUE_SEASON != PREFERRED_VALUE_SEASON:
        warnings.append(
            f"using cached valuation season {DEFAULT_VALUE_SEASON} instead of preferred "
            f"{PREFERRED_VALUE_SEASON}"
        )
    all_ids = set(req.give_player_ids) | set(req.get_player_ids)

    if all_ids:
        try:
            with SleeperClient() as client:
                sleeper_players = client.players()
            assets = build_player_assets(seasons=seasons, sleeper_players=sleeper_players)
        except Exception as exc:
            log.exception("failed to build player assets for trade analysis")
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        asset_map = {p.player_id: p for p in assets}
        for pid in all_ids - set(asset_map):
            fallback = _rookie_asset_from_sleeper(pid, sleeper_players)
            if fallback is not None:
                asset_map[pid] = fallback
    else:
        asset_map = {}

    missing_player_ids = sorted(pid for pid in all_ids if pid not in asset_map)
    if missing_player_ids:
        raise _http_400(
            {
                "error": "unknown_or_unvalued_player_ids",
                "missing_player_ids": missing_player_ids,
                "message": "Every selected player must be valued before a verdict is returned.",
            }
        )

    from sleeper_ffm.market.blend import blended_value, build_player_blend, pick_market_available

    give_players = [asset_map[pid] for pid in req.give_player_ids]
    get_players = [asset_map[pid] for pid in req.get_player_ids]

    blend = build_player_blend(list(asset_map.values())) if all_ids else None

    def _player_breakdown(assets: list[PlayerAsset]) -> tuple[list[dict], float]:
        rows: list[dict] = []
        subtotal = 0.0
        for p in assets:
            model_value = value_player(p)
            if blend is not None:
                dyn, market_valued = blended_value(p.player_id, p.position, model_value, blend)
                market_dyn = blend.market_dyn(p.player_id)
                market_value = (
                    round(market_dyn, 2) if market_valued and market_dyn is not None else None
                )
            else:
                dyn, market_value = model_value, None
            subtotal += dyn
            rows.append(
                {
                    "player_id": p.player_id,
                    "name": p.name,
                    "position": p.position,
                    "model_value": round(model_value, 2),
                    "market_value": market_value,
                    "blended_value": dyn,
                }
            )
        return rows, subtotal

    give_breakdown, give_players_value = _player_breakdown(give_players)
    get_breakdown, get_players_value = _player_breakdown(get_players)

    give_value = give_players_value + sum(value_trade_pick(pid) for pid in req.give_pick_ids)
    get_value = get_players_value + sum(value_trade_pick(pid) for pid in req.get_pick_ids)
    delta = get_value - give_value
    verdict = "ACCEPT" if delta > 10 else "DECLINE" if delta < -10 else "CLOSE"

    prompt = build_trade_prompt(
        give_player_ids=req.give_player_ids,
        get_player_ids=req.get_player_ids,
        give_pick_ids=req.give_pick_ids,
        get_pick_ids=req.get_pick_ids,
        seasons=seasons,
    )

    if blend is not None and blend.model_valued_only:
        warnings.append("FantasyCalc market unavailable; values are model-only, not blended.")
    if (req.give_pick_ids or req.get_pick_ids) and not pick_market_available():
        warnings.append(
            "FantasyCalc pick market unavailable; pick values use the static fallback table."
        )

    return {
        "give_value": round(give_value, 2),
        "get_value": round(get_value, 2),
        "delta": round(delta, 2),
        "verdict": verdict,
        "give_breakdown": give_breakdown,
        "get_breakdown": get_breakdown,
        "currency": "model-only" if blend is None or blend.model_valued_only else "blended",
        "data_quality": "DEGRADED" if warnings else "FULL",
        "warnings": warnings,
        "prompt": prompt,
    }


@router.get("/offers")
def trade_offers(top: int = 8) -> list[dict]:
    """Return acceptance-scored outgoing trade offer recommendations."""
    from sleeper_ffm.model.trade_acceptance import recommend_trade_offers

    try:
        return [dataclasses.asdict(offer) for offer in recommend_trade_offers(top=top)]
    except Exception as exc:
        log.exception("failed to build trade offer recommendations")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/picks")
def my_traded_picks() -> list[dict]:
    """Return traded picks currently held by Rob's roster (owner_id == MY_ROSTER_ID).

    Each pick carries a backend-computed dynasty ``value`` so the UI never
    re-derives pick values client-side.
    """
    from sleeper_ffm.model.dynasty import PickAsset, value_pick
    from sleeper_ffm.sleeper.client import SleeperClient

    with SleeperClient() as c:
        all_picks = c.traded_picks()

    out: list[dict] = []
    for p in all_picks:
        if p.owner_id != MY_ROSTER_ID:
            continue
        row = p.model_dump()
        row["value"] = round(
            value_pick(
                PickAsset(
                    season=str(p.season),
                    round=int(p.round),
                    original_owner_id=p.roster_id,
                    current_owner_id=MY_ROSTER_ID,
                )
            ),
            1,
        )
        out.append(row)
    return out
