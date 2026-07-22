"""FastAPI router — in-season analysis (waivers, streaming targets, trends)."""

from __future__ import annotations

import contextlib
import dataclasses
import logging

from fastapi import APIRouter, Query

from sleeper_ffm.config import DEFAULT_VALUE_SEASON, MY_ROSTER_ID
from sleeper_ffm.model.faab_market import build_faab_market
from sleeper_ffm.model.trends import compute_trends
from sleeper_ffm.season.startsit import build_startsit
from sleeper_ffm.season.waivers import analyze_waivers
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

router = APIRouter(prefix="/season", tags=["season"])


@router.get("/waivers")
def waivers(top: int = Query(default=25)) -> list[dict]:
    """Top trending waiver-wire targets with priority scores and FAAB estimates.

    Fetches 24-hour trending adds and drops from Sleeper, scores each unrostered
    skill-position player, and returns the top candidates.

    Args:
        top: Number of candidates to return (default 25).

    Returns:
        List of waiver candidate dicts sorted by add_priority descending.
    """
    with SleeperClient() as c:
        trending_adds = c.trending("add", lookback_hours=24, limit=50)
        trending_drops = c.trending("drop", lookback_hours=24, limit=50)
        sleeper_players = c.players()
        rosters = c.rosters()

    rostered_ids: set[str] = set()
    my_roster_ids: set[str] = set()
    protected_ids: set[str] = set()
    for roster in rosters:
        rostered_ids.update(roster.players)
        if roster.roster_id == MY_ROSTER_ID:
            my_roster_ids.update(roster.players)
            protected_ids.update(roster.starters)

    try:
        faab_market = build_faab_market()
    except Exception as exc:
        log.warning("waivers: faab market unavailable: %s", exc)
        faab_market = None

    candidates = analyze_waivers(
        sleeper_players=sleeper_players,
        trending_adds=trending_adds,
        trending_drops=trending_drops,
        rostered_ids=rostered_ids,
        my_roster_ids=my_roster_ids,
        protected_ids=protected_ids,
        faab_market=faab_market,
    )

    return [dataclasses.asdict(c) for c in candidates[:top]]


@router.get("/startsit")
def startsit(
    week: int = Query(default=0, description="NFL week (0 = current)"),
    season: int = Query(default=DEFAULT_VALUE_SEASON, description="NFL season year"),
) -> dict:
    """Optimal start/sit lineup for Rob's roster.

    Projects each skill-position player's expected points using nflverse weekly
    averages, falls back to dynasty value proxy for players without recent data.

    Args:
        week: NFL week to optimize for (0 = use current week from Sleeper state).
        season: NFL season year.

    Returns:
        StartSitRecommendation as a dict: projected_starters, current_starters, changes,
        and projected totals. (No separate LLM prompt — start/sit reasoning is a task in
        the single master briefing; see prompts/master.py.)
    """
    resolved_week = week
    if resolved_week == 0:
        with SleeperClient() as c:
            state = c.state_nfl()
        resolved_week = state.week or 1
        if season == DEFAULT_VALUE_SEASON and state.season:
            with contextlib.suppress(ValueError):
                season = int(state.season)
    rec = build_startsit(week=resolved_week, season=season)
    return dataclasses.asdict(rec)


@router.get("/trends")
def trends(top: int = Query(default=30), direction: str = Query(default="ALL")) -> list[dict]:
    """Target-share and FPAR trend signals for breakout and decline candidates.

    Args:
        top: Maximum number of results to return.
        direction: Filter by direction — RISING, FALLING, or ALL (default).

    Returns:
        List of TrendSignal dicts sorted by signal_strength descending.
    """
    signals = compute_trends()
    direction_upper = direction.upper()
    if direction_upper != "ALL":
        signals = [s for s in signals if s.direction == direction_upper]
    return [dataclasses.asdict(s) for s in signals[:top]]
