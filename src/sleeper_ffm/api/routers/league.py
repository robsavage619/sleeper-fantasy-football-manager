"""FastAPI router — league, rosters, picks, matchups."""

from __future__ import annotations

from fastapi import APIRouter

from sleeper_ffm.sleeper.client import SleeperClient

router = APIRouter(prefix="/league", tags=["league"])


@router.get("/")
def league_info() -> dict:
    """Live league metadata from Sleeper."""
    with SleeperClient() as c:
        lg = c.league()
    return lg.model_dump()


@router.get("/rosters")
def rosters() -> list[dict]:
    """All rosters with player lists."""
    with SleeperClient() as c:
        return [r.model_dump() for r in c.rosters()]


@router.get("/users")
def users() -> list[dict]:
    """All league members."""
    with SleeperClient() as c:
        return [u.model_dump() for u in c.users()]


@router.get("/traded-picks")
def traded_picks() -> list[dict]:
    """Current traded draft pick inventory."""
    with SleeperClient() as c:
        return [p.model_dump() for p in c.traded_picks()]


@router.get("/matchups/{week}")
def matchups(week: int) -> list[dict]:
    """Matchups for a scoring week (includes players_points)."""
    with SleeperClient() as c:
        return c.matchups(week)


@router.get("/state")
def nfl_state() -> dict:
    """Current NFL calendar state (week, season_type)."""
    with SleeperClient() as c:
        return c.state_nfl().model_dump()


@router.get("/trending/{kind}")
def trending(kind: str, hours: int = 24, limit: int = 25) -> list[dict]:
    """Trending add or drop players with resolved name and position."""
    with SleeperClient() as c:
        results = c.trending(kind, lookback_hours=hours, limit=limit)
        players = c.players()

    out = []
    for t in results:
        sp = players.get(t.player_id, {})
        out.append({
            "player_id": t.player_id,
            "count": t.count,
            "name": sp.get("full_name") or sp.get("last_name") or t.player_id,
            "position": sp.get("position") or "",
            "team": sp.get("team") or "FA",
        })
    return out
