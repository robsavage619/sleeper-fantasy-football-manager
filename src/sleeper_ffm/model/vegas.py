"""Vegas game-environment layer — implied team totals and blowout risk.

Turns the ``spread_line``/``total_line`` columns already sitting unused in the cached
nflverse schedule parquet into a per-team-per-week scoring-environment index: how many
points is this team's offense implied to score, and how lopsided is the game expected
to be. Used as a light multiplier on player projections elsewhere (start/sit, gameday)
— a team in a shootout scores more across the board; a team implied to be blown out
scores less. This is a global offense-level prior, not a positional game-script model:
no attempt is made here to claim "which position benefits from garbage time" — that
needs more than a spread number to support.

Sign convention (verified against 2024 completed games — corr(result, spread_line) =
+0.50, and implied totals back out actual scores with ~0 bias): ``spread_line`` is the
home team's expected margin — positive means the home team is favored by that many
points. ``total_line`` is the game's combined expected total.

    implied_home_total = (total_line + spread_line) / 2
    implied_away_total = (total_line - spread_line) / 2
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

import polars as pl

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.nflverse.loader import load_schedules

log = logging.getLogger(__name__)

# Fantasy playoff weeks — where a shootout-implied schedule matters most.
PLAYOFF_WEEKS: tuple[int, ...] = (15, 16, 17)

# Clamp the environment multiplier so one outlier line can't swing a projection more
# than this — same "index, not a projection" philosophy as schedule_strength's DvP.
_MULTIPLIER_FLOOR = 0.80
_MULTIPLIER_CEILING = 1.25


@dataclass
class TeamGameEnvironment:
    """One team's Vegas-implied scoring environment for one game."""

    season: int
    week: int
    team: str
    opponent: str
    is_home: bool
    implied_total: float | None  # this team's implied points
    opponent_implied_total: float | None
    team_spread: float | None  # positive = favored by this many points
    game_total: float | None  # total_line, the game's combined implied points
    blowout_risk: float | None  # 0-1, how lopsided the expected game is


@dataclass
class SeasonEnvironment:
    """Full per-team-per-week environment surface for a season."""

    season: int
    games: list[TeamGameEnvironment]
    league_avg_implied_total: float | None
    warnings: list[str] = field(default_factory=list)


def implied_totals(spread_line: float, total_line: float) -> tuple[float, float]:
    """Return ``(home_implied, away_implied)`` from a game's spread and total.

    Args:
        spread_line: Home team's expected margin (positive = home favored).
        total_line: Game's combined expected point total.

    Returns:
        Each team's implied point total, rounded to 2 decimals.
    """
    return (
        round((total_line + spread_line) / 2, 2),
        round((total_line - spread_line) / 2, 2),
    )


def blowout_risk(team_spread: float | None, game_total: float | None) -> float | None:
    """0-1 index: how lopsided the game is expected to be.

    A 14-point spread in a 55-point shootout plays very differently than the same
    spread in a 33-point grind, so the spread is judged relative to the total rather
    than in isolation. Clipped to ``[0, 1]``; ``None`` when either input is missing.

    Args:
        team_spread: A team's expected margin (sign doesn't matter — risk is symmetric).
        game_total: The game's combined expected total.

    Returns:
        Blowout-risk index, or ``None`` if odds aren't published.
    """
    if team_spread is None or not game_total:
        return None
    return round(min(1.0, abs(team_spread) / (game_total * 0.35)), 3)


def build_season_environment(season: int) -> SeasonEnvironment:
    """Build per-team-per-week Vegas environment for a season.

    Args:
        season: NFL season year.

    Returns:
        A :class:`SeasonEnvironment`. Games with unpublished odds still appear with
        ``None`` numeric fields rather than being dropped, so callers can see what's
        missing rather than silently getting a partial schedule.
    """
    try:
        sched = load_schedules(seasons=[season])
    except Exception as exc:
        log.warning("vegas: schedule %d unavailable: %s", season, exc)
        return SeasonEnvironment(
            season=season,
            games=[],
            league_avg_implied_total=None,
            warnings=[f"Schedule for {season} unavailable: {exc}"],
        )

    cols = {"season", "week", "home_team", "away_team", "game_type", "spread_line", "total_line"}
    if sched.is_empty() or not cols.issubset(sched.columns):
        return SeasonEnvironment(
            season=season,
            games=[],
            league_avg_implied_total=None,
            warnings=[f"Schedule for {season} missing required columns."],
        )

    reg = sched.filter((pl.col("season") == season) & (pl.col("game_type") == "REG"))

    games: list[TeamGameEnvironment] = []
    totals_seen: list[float] = []
    for row in reg.iter_rows(named=True):
        home, away = row.get("home_team"), row.get("away_team")
        if not home or not away:
            continue
        wk = int(row["week"])
        spread, total = row.get("spread_line"), row.get("total_line")

        home_implied = away_implied = None
        if spread is not None and total is not None:
            home_implied, away_implied = implied_totals(float(spread), float(total))
            totals_seen.extend([home_implied, away_implied])

        away_spread = -float(spread) if spread is not None else None
        games.append(
            TeamGameEnvironment(
                season=season,
                week=wk,
                team=home,
                opponent=away,
                is_home=True,
                implied_total=home_implied,
                opponent_implied_total=away_implied,
                team_spread=spread,
                game_total=total,
                blowout_risk=blowout_risk(spread, total),
            )
        )
        games.append(
            TeamGameEnvironment(
                season=season,
                week=wk,
                team=away,
                opponent=home,
                is_home=False,
                implied_total=away_implied,
                opponent_implied_total=home_implied,
                team_spread=away_spread,
                game_total=total,
                blowout_risk=blowout_risk(away_spread, total),
            )
        )

    warnings = [] if totals_seen else [f"No published odds yet for {season}."]
    league_avg = round(statistics.mean(totals_seen), 2) if totals_seen else None
    return SeasonEnvironment(
        season=season, games=games, league_avg_implied_total=league_avg, warnings=warnings
    )


@ttl_cache()
def build_environment_index(season: int) -> SeasonEnvironment:
    """Cached wrapper around :func:`build_season_environment`."""
    return build_season_environment(season)


def team_week_environment(season: int, week: int, team: str) -> TeamGameEnvironment | None:
    """Look up one team's environment for one week, or ``None`` if not scheduled."""
    env = build_environment_index(season)
    return next((g for g in env.games if g.week == week and g.team == team), None)


def environment_multiplier(season: int, week: int, team: str) -> float:
    """Scalar prior for a team's expected scoring environment; ~1.0 = league average.

    Intended to lightly scale player projections: a team implied to score well above
    league average gets a small bump, a team implied to score well below gets a small
    fade. Clamped to ``[_MULTIPLIER_FLOOR, _MULTIPLIER_CEILING]``; defaults to ``1.0``
    (no adjustment) when the game isn't found or odds aren't published yet.

    Args:
        season: NFL season year.
        week: NFL week.
        team: Team abbreviation as used in nflverse schedules.

    Returns:
        Multiplier to apply to a player's baseline projection.
    """
    env = build_environment_index(season)
    game = next((g for g in env.games if g.week == week and g.team == team), None)
    if game is None or game.implied_total is None or not env.league_avg_implied_total:
        return 1.0
    raw = game.implied_total / env.league_avg_implied_total
    return round(min(_MULTIPLIER_CEILING, max(_MULTIPLIER_FLOOR, raw)), 3)


def playoff_environment(season: int, team: str) -> dict:
    """Aggregate implied total + blowout risk over the fantasy playoff weeks.

    Args:
        season: NFL season year.
        team: Team abbreviation.

    Returns:
        Dict with ``weeks_counted``, ``avg_implied_total``, ``avg_blowout_risk``
        (``None`` values where odds aren't published for those weeks yet).
    """
    env = build_environment_index(season)
    rows = [g for g in env.games if g.team == team and g.week in PLAYOFF_WEEKS]
    totals = [g.implied_total for g in rows if g.implied_total is not None]
    risks = [g.blowout_risk for g in rows if g.blowout_risk is not None]
    return {
        "team": team,
        "season": season,
        "weeks_counted": len(totals),
        "avg_implied_total": round(statistics.mean(totals), 2) if totals else None,
        "avg_blowout_risk": round(statistics.mean(risks), 3) if risks else None,
    }
