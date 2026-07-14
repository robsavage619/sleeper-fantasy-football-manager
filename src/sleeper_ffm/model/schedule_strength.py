"""Defense-vs-position ratings and rest-of-season / playoff strength of schedule.

Two deterministic layers that replace the "consider matchups" hand-wave in the
start/sit prompt with numbers:

    1. **Defense-vs-position (DvP).** From the latest completed season scored under
       this league's rules, how many fantasy points each defense allowed to each
       position per game, indexed against the league average. ``index > 1`` = a soft
       matchup for that position; ``< 1`` = a tough one.

    2. **Strength of schedule (SoS).** For an upcoming season's schedule, aggregate the
       opponents' DvP indices over a set of weeks — full season and, critically for
       dynasty, the fantasy playoff weeks (15-17). A high playoff SoS is a concrete
       reason to acquire a player whose team draws soft defenses in December.

DvP is computed off the *prior* season (the only completed data); SoS maps it onto the
*upcoming* schedule. That is the standard, honest approximation — defenses carry over
imperfectly, so the module labels itself a lean, not a projection.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

import polars as pl

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.config import CURRENT_LEAGUE_YEAR, DEFAULT_VALUE_SEASON
from sleeper_ffm.model.valuation import SKILL_POSITIONS, score_weekly
from sleeper_ffm.nflverse.loader import load_schedules

log = logging.getLogger(__name__)

# Fantasy playoff weeks in a standard dynasty league — where schedule matters most.
PLAYOFF_WEEKS: tuple[int, ...] = (15, 16, 17)
# A DvP sample needs at least this many games before the index is trusted.
_MIN_DEF_GAMES: int = 4


@dataclass
class TeamPositionSoS:
    """One team's schedule softness for one position."""

    team: str
    position: str
    full_season_index: float  # mean opponent DvP over all scheduled weeks
    playoff_index: float  # mean opponent DvP over PLAYOFF_WEEKS
    weeks_counted: int
    playoff_weeks_counted: int
    softest_week: dict | None = None  # {week, opponent, index}
    toughest_week: dict | None = None


@dataclass
class ScheduleStrength:
    """Full DvP + SoS surface for a season."""

    dvp_season: int
    schedule_season: int
    dvp: dict[str, float]  # "TEAM|POS" -> index (JSON-safe flat key)
    sos: list[TeamPositionSoS]
    warnings: list[str] = field(default_factory=list)


def compute_dvp(scored: pl.DataFrame) -> dict[tuple[str, str], float]:
    """Compute defense-vs-position indices from scored weekly data.

    Args:
        scored: Output of ``score_weekly`` — REG rows with ``fp_sffm``,
            ``opponent_team``, ``position``, ``season``, ``week``.

    Returns:
        ``{(defense_team, position): index}`` where index = points allowed to that
        position per game / league-average points allowed to that position per game.
    """
    needed = {"fp_sffm", "opponent_team", "position", "week", "season"}
    if scored.is_empty() or not needed.issubset(scored.columns):
        return {}

    pos_df = scored.filter(pl.col("position").is_in(list(SKILL_POSITIONS)))
    if pos_df.is_empty():
        return {}

    # Points a position put up against each defense, per game.
    per_game = pos_df.group_by(["opponent_team", "position", "season", "week"]).agg(
        pl.col("fp_sffm").sum().alias("pts_allowed")
    )
    per_def = per_game.group_by(["opponent_team", "position"]).agg(
        [
            pl.col("pts_allowed").mean().alias("allowed_pg"),
            pl.col("pts_allowed").len().alias("games"),
        ]
    )

    league_avg: dict[str, float] = {}
    for pos in SKILL_POSITIONS:
        vals = per_def.filter(pl.col("position") == pos)["allowed_pg"].to_list()
        if vals:
            league_avg[pos] = statistics.mean(vals)

    dvp: dict[tuple[str, str], float] = {}
    for row in per_def.iter_rows(named=True):
        pos = row["position"]
        team = row["opponent_team"]
        avg = league_avg.get(pos)
        if not team or not avg or row["games"] < _MIN_DEF_GAMES:
            continue
        dvp[(team, pos)] = round(row["allowed_pg"] / avg, 3)
    return dvp


def schedule_softness(
    weekly_opponents: list[tuple[int, str]],
    position: str,
    dvp: dict[tuple[str, str], float],
    weeks: tuple[int, ...] | None = None,
) -> tuple[float, int]:
    """Average opponent DvP index over the given weeks.

    Args:
        weekly_opponents: ``[(week, opponent_team), ...]`` for one team's schedule.
        position: Position to evaluate the matchups for.
        dvp: DvP map from :func:`compute_dvp`.
        weeks: Restrict to these weeks (e.g. ``PLAYOFF_WEEKS``); None = all weeks.

    Returns:
        ``(mean_index, weeks_counted)``. Index defaults to 1.0 for opponents without a
        DvP sample so they neither help nor hurt. Returns ``(1.0, 0)`` if nothing counts.
    """
    indices: list[float] = []
    for week, opp in weekly_opponents:
        if weeks is not None and week not in weeks:
            continue
        if not opp:
            continue
        indices.append(dvp.get((opp, position), 1.0))
    if not indices:
        return 1.0, 0
    return round(statistics.mean(indices), 3), len(indices)


def _team_schedules(schedule_season: int) -> dict[str, list[tuple[int, str]]]:
    """Return ``{team: [(week, opponent), ...]}`` for a season, or {} if unavailable."""
    try:
        sched = load_schedules(seasons=[schedule_season])
    except Exception as exc:
        log.warning("schedule_strength: schedule %d unavailable: %s", schedule_season, exc)
        return {}
    cols = {"season", "week", "home_team", "away_team", "game_type"}
    if sched.is_empty() or not cols.issubset(sched.columns):
        return {}
    reg = sched.filter((pl.col("season") == schedule_season) & (pl.col("game_type") == "REG"))
    out: dict[str, list[tuple[int, str]]] = {}
    for row in reg.iter_rows(named=True):
        wk, home, away = row["week"], row["home_team"], row["away_team"]
        if home and away:
            out.setdefault(home, []).append((int(wk), away))
            out.setdefault(away, []).append((int(wk), home))
    return out


@ttl_cache()
def build_schedule_strength(
    dvp_season: int | None = None,
    schedule_season: int | None = None,
) -> ScheduleStrength:
    """Build the DvP + SoS surface.

    Args:
        dvp_season: Season to derive DvP from (default: latest completed).
        schedule_season: Season whose schedule to grade (default: current league year).

    Returns:
        A :class:`ScheduleStrength`. Degrades gracefully (empty ``sos`` with a warning)
        when the upcoming schedule is not yet published.
    """
    dvp_season = dvp_season or DEFAULT_VALUE_SEASON
    schedule_season = schedule_season or CURRENT_LEAGUE_YEAR
    warnings: list[str] = []

    scored = score_weekly(seasons=[dvp_season])
    dvp = compute_dvp(scored)
    if not dvp:
        warnings.append(f"No DvP could be computed for {dvp_season}.")

    team_scheds = _team_schedules(schedule_season)
    if not team_scheds:
        warnings.append(
            f"Schedule for {schedule_season} unavailable; SoS omitted (DvP still returned)."
        )

    sos: list[TeamPositionSoS] = []
    for team, weekly_opps in sorted(team_scheds.items()):
        for pos in SKILL_POSITIONS:
            full_idx, full_n = schedule_softness(weekly_opps, pos, dvp)
            po_idx, po_n = schedule_softness(weekly_opps, pos, dvp, weeks=PLAYOFF_WEEKS)
            rated = [
                {"week": wk, "opponent": opp, "index": dvp.get((opp, pos), 1.0)}
                for wk, opp in weekly_opps
                if (opp, pos) in dvp
            ]
            softest = max(rated, key=lambda r: r["index"]) if rated else None
            toughest = min(rated, key=lambda r: r["index"]) if rated else None
            sos.append(
                TeamPositionSoS(
                    team=team,
                    position=pos,
                    full_season_index=full_idx,
                    playoff_index=po_idx,
                    weeks_counted=full_n,
                    playoff_weeks_counted=po_n,
                    softest_week=softest,
                    toughest_week=toughest,
                )
            )

    return ScheduleStrength(
        dvp_season=dvp_season,
        schedule_season=schedule_season,
        dvp={f"{team}|{pos}": idx for (team, pos), idx in dvp.items()},
        sos=sos,
        warnings=warnings,
    )
