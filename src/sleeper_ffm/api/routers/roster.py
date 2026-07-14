"""FastAPI router — dynasty roster values and league-wide roster summary."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from sleeper_ffm.config import DEFAULT_VALUE_SEASON, MY_ROSTER_ID
from sleeper_ffm.market.blend import MarketBlend, blended_value, build_player_blend
from sleeper_ffm.model.dynasty import PlayerAsset, value_player
from sleeper_ffm.model.valuation import (
    SKILL_POSITIONS,
    _rookie_fpar,
    build_player_assets_cached,
)
from sleeper_ffm.sleeper.client import SleeperClient
from sleeper_ffm.sleeper.models import Roster

log = logging.getLogger(__name__)

router = APIRouter(prefix="/roster", tags=["roster"])


def _build_player_rows(
    roster: Roster,
    vet_map: dict[str, PlayerAsset],
    sleeper_players: dict[str, dict],
    blend: MarketBlend | None = None,
) -> list[dict]:
    """Build valued player rows for a single roster.

    Args:
        roster: Sleeper Roster model.
        vet_map: player_id → PlayerAsset built from build_player_assets.
        sleeper_players: Full Sleeper player dump.
        blend: Optional market blend. When provided, ``dynasty_value`` is the
            model/market blend and rows carry ``model_value``/``market_value``.

    Returns:
        List of player dicts sorted by dynasty_value descending.
        Only SKILL_POSITIONS are included.
    """
    starters_set = set(roster.starters)
    taxi_set = set(roster.taxi or [])
    reserve_set = set(roster.reserve or [])

    rows: list[dict] = []
    for pid in roster.players:
        sp = sleeper_players.get(pid, {})
        pos = sp.get("position", "")
        if pos not in SKILL_POSITIONS:
            continue

        is_taxi = pid in taxi_set
        is_reserve = pid in reserve_set
        is_starter = pid in starters_set

        if pid in vet_map:
            base = vet_map[pid]
            asset = PlayerAsset(
                player_id=base.player_id,
                name=base.name,
                position=base.position,
                age=base.age,
                current_fpar=base.current_fpar,
                team=base.team,
                is_taxi=is_taxi,
                is_reserve=is_reserve,
            )
        else:
            search_rank: int | None = sp.get("search_rank")
            fpar = _rookie_fpar(search_rank) if search_rank is not None else 5.0
            asset = PlayerAsset(
                player_id=pid,
                name=sp.get("full_name") or f"Player {pid}",
                position=pos,
                age=float(sp.get("age") or 22),
                current_fpar=fpar,
                team=sp.get("team") or "",
                is_taxi=is_taxi,
                is_reserve=is_reserve,
            )

        model_value = value_player(asset)
        market_value: float | None = None
        if blend is not None:
            dynasty_value, market_valued = blended_value(pid, asset.position, model_value, blend)
            if market_valued:
                market_dyn = blend.market_dyn(pid)
                market_value = round(market_dyn, 2) if market_dyn is not None else None
        else:
            dynasty_value = model_value
            market_valued = False
        rows.append(
            {
                "player_id": pid,
                "name": asset.name,
                "position": asset.position,
                "age": asset.age,
                "team": asset.team,
                "fpar": asset.current_fpar,
                "dynasty_value": dynasty_value,
                "model_value": model_value,
                "market_value": market_value,
                "market_valued": market_valued,
                "is_starter": is_starter,
                "is_taxi": is_taxi,
                "is_reserve": is_reserve,
            }
        )

    return sorted(rows, key=lambda x: x["dynasty_value"], reverse=True)


@router.get("/my")
def my_roster(season: int = Query(default=DEFAULT_VALUE_SEASON)) -> dict:
    """Rob's current roster with dynasty values for each skill-position player.

    Args:
        season: NFL season year to use for FPAR computation.

    Returns:
        Roster summary with per-player dynasty values, sorted by value descending.
    """
    with SleeperClient() as c:
        rosters = c.rosters()
        sleeper_players = c.players()

    my_roster_obj = next((r for r in rosters if r.roster_id == MY_ROSTER_ID), None)
    if my_roster_obj is None:
        return {"error": f"roster_id {MY_ROSTER_ID} not found"}

    log.info("building player assets for my roster, season=%d", season)
    vet_assets = build_player_assets_cached(seasons=[season], sleeper_players=sleeper_players)
    vet_map = {a.player_id: a for a in vet_assets}
    blend = build_player_blend(vet_assets)

    player_rows = _build_player_rows(my_roster_obj, vet_map, sleeper_players, blend=blend)
    total_value = round(sum(p["dynasty_value"] for p in player_rows), 2)

    return {
        "roster_id": MY_ROSTER_ID,
        "total_players": len(player_rows),
        "total_dynasty_value": total_value,
        "players": player_rows,
    }


@router.get("/all")
def all_rosters(season: int = Query(default=DEFAULT_VALUE_SEASON)) -> list[dict]:
    """All league rosters with dynasty value summaries.

    Args:
        season: NFL season year to use for FPAR computation.

    Returns:
        List of roster summaries sorted by total_dynasty_value descending.
        Each entry includes roster_id, owner_id, player_count,
        total_dynasty_value, starters count, and top_3_players.
    """
    with SleeperClient() as c:
        rosters = c.rosters()
        sleeper_players = c.players()

    log.info("building player assets for all rosters, season=%d", season)
    vet_assets = build_player_assets_cached(seasons=[season], sleeper_players=sleeper_players)
    vet_map = {a.player_id: a for a in vet_assets}
    blend = build_player_blend(vet_assets)

    results: list[dict] = []
    for roster in rosters:
        player_rows = _build_player_rows(roster, vet_map, sleeper_players, blend=blend)
        total_value = round(sum(p["dynasty_value"] for p in player_rows), 2)
        starter_count = sum(1 for p in player_rows if p["is_starter"])
        top_3 = [
            {"name": p["name"], "position": p["position"], "value": p["dynasty_value"]}
            for p in player_rows[:3]
        ]
        results.append(
            {
                "roster_id": roster.roster_id,
                "owner_id": roster.owner_id,
                "player_count": len(player_rows),
                "total_dynasty_value": total_value,
                "starters": starter_count,
                "top_3_players": top_3,
            }
        )

    return sorted(results, key=lambda x: x["total_dynasty_value"], reverse=True)
