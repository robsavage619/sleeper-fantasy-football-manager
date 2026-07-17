"""FastAPI router — Vegas-implied game environment (team totals, blowout risk)."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException, Query

from sleeper_ffm.config import CURRENT_LEAGUE_YEAR
from sleeper_ffm.model.vegas import build_environment_index, playoff_environment

log = logging.getLogger(__name__)

router = APIRouter(prefix="/vegas", tags=["vegas"])

_SEASON_QUERY = Query(default=None)
_WEEK_QUERY = Query(default=None)
_TEAM_QUERY = Query(default=None)


@router.get("")
def vegas_environment(
    season: int | None = _SEASON_QUERY,
    week: int | None = _WEEK_QUERY,
    team: str | None = _TEAM_QUERY,
) -> dict:
    """Return per-team-per-week Vegas-implied scoring environment (optionally filtered)."""
    try:
        env = build_environment_index(season or CURRENT_LEAGUE_YEAR)
        games = env.games
        if week is not None:
            games = [g for g in games if g.week == week]
        if team:
            t = team.upper()
            games = [g for g in games if g.team == t]
        return {
            "season": env.season,
            "league_avg_implied_total": env.league_avg_implied_total,
            "games": [dataclasses.asdict(g) for g in games],
            "warnings": env.warnings,
            "data_quality": "DEGRADED" if env.warnings else "FULL",
        }
    except Exception as exc:
        log.exception("vegas environment failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/playoffs")
def vegas_playoffs(season: int | None = _SEASON_QUERY) -> dict:
    """Return the fantasy-playoff-weeks (15-17) environment aggregate for every team."""
    try:
        s = season or CURRENT_LEAGUE_YEAR
        env = build_environment_index(s)
        teams = sorted({g.team for g in env.games})
        return {
            "season": s,
            "teams": [playoff_environment(s, t) for t in teams],
            "warnings": env.warnings,
            "data_quality": "DEGRADED" if env.warnings else "FULL",
        }
    except Exception as exc:
        log.exception("vegas playoffs failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
