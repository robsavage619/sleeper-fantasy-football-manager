"""Live gameday co-pilot — win probability and pre-lock lineup edge for my matchup.

The Sunday-morning surface: given this week's head-to-head, how likely am I to win as
lineups stand, and is there a legal lineup change that raises that number before kickoff?

    * **Win probability** models the margin as normal — my projected total minus my
      opponent's, with the two teams' scoring variances combined — and reads off the
      chance the margin is positive (:func:`win_probability`). Pure and exact.
    * **Pre-lock edge** reuses the start/sit optimizer to surface any point-gaining swap
      still available before the lineup locks.

Off-season degrades cleanly: with no live matchup published, the brief returns a note
rather than fabricating an opponent.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from sleeper_ffm.config import CURRENT_LEAGUE_YEAR, DEFAULT_VALUE_SEASON, MY_ROSTER_ID
from sleeper_ffm.model.season_sim import _STD_FLOOR, _STD_FRACTION, _lineup_strength
from sleeper_ffm.model.vegas import environment_multiplier

log = logging.getLogger(__name__)


@dataclass
class GamedayBrief:
    """This week's matchup outlook."""

    week: int
    season: int
    has_matchup: bool
    my_roster_id: int
    opponent_roster_id: int | None
    my_projected: float
    opponent_projected: float
    win_probability: float
    lineup_upside: float  # points a legal pre-lock swap would add (0 if optimal)
    recommended_swaps: list[dict]  # from the start/sit optimizer
    note: str = ""
    warnings: list[str] = field(default_factory=list)


def win_probability(my_mean: float, opp_mean: float, my_std: float, opp_std: float) -> float:
    """Probability my team outscores the opponent, modeling the margin as normal.

    Args:
        my_mean: My projected points.
        opp_mean: Opponent's projected points.
        my_std: My weekly scoring standard deviation.
        opp_std: Opponent's weekly scoring standard deviation.

    Returns:
        ``P(my_score > opp_score)`` in ``[0, 1]``. Falls back to a step function at the
        mean when both variances are zero.
    """
    combined_sd = math.sqrt(my_std**2 + opp_std**2)
    if combined_sd <= 0:
        if my_mean == opp_mean:
            return 0.5
        return 1.0 if my_mean > opp_mean else 0.0
    z = (my_mean - opp_mean) / combined_sd
    return round(0.5 * (1.0 + math.erf(z / math.sqrt(2))), 4)


def _team_strength(
    roster,
    players: dict[str, dict],
    per_game_fp: dict[str, float],
    season: int,
    week: int,
) -> float:
    """Weekly projected points for a roster's optimal lineup of per-game FP.

    Each player's per-game average is lightly scaled by their team's Vegas-implied
    scoring environment for this week (:func:`environment_multiplier`).
    """
    from sleeper_ffm.model.season_sim import _FLEX_POS

    pg: dict[str, tuple[str, float]] = {}
    for pid in roster.players or []:
        meta = players.get(pid, {})
        pos = meta.get("position")
        if pos in _FLEX_POS or pos == "QB":
            mult = environment_multiplier(season, week, meta.get("team") or "")
            pg[pid] = (pos, per_game_fp.get(pid, 0.0) * mult)
    return max(_lineup_strength(pg), _STD_FLOOR)


def build_gameday(week: int, my_roster_id: int = MY_ROSTER_ID) -> GamedayBrief:
    """Build the gameday brief for a week.

    Degrades to ``has_matchup=False`` with a note when no live matchup is published
    (the normal off-season case).
    """
    from sleeper_ffm.model.valuation import compute_season_totals
    from sleeper_ffm.sleeper.client import SleeperClient

    warnings: list[str] = []
    with SleeperClient() as c:
        rosters = c.rosters()
        players = c.players()
        try:
            matchups = c.matchups(week)
        except Exception as exc:
            log.info("gameday: no matchups for week %d (%s)", week, exc)
            matchups = []

    totals = compute_season_totals(seasons=[DEFAULT_VALUE_SEASON])
    per_game_fp: dict[str, float] = {}
    if not totals.is_empty() and "sleeper_id_str" in totals.columns:
        for row in totals.iter_rows(named=True):
            sid = row.get("sleeper_id_str")
            if sid:
                per_game_fp[sid] = float(row.get("season_fp") or 0.0) / 17.0

    roster_by_id = {r.roster_id: r for r in rosters}
    my_matchup = next((m for m in matchups if m.get("roster_id") == my_roster_id), None)
    opp_id: int | None = None
    if my_matchup is not None:
        mid = my_matchup.get("matchup_id")
        opp = next(
            (
                m
                for m in matchups
                if m.get("matchup_id") == mid and m.get("roster_id") != my_roster_id
            ),
            None,
        )
        opp_id = opp.get("roster_id") if opp else None

    if opp_id is None or my_roster_id not in roster_by_id:
        warnings.append(
            f"No live matchup for week {week} (off-season or schedule unpublished); "
            "win probability unavailable."
        )
        return GamedayBrief(
            week=week,
            season=DEFAULT_VALUE_SEASON,
            has_matchup=False,
            my_roster_id=my_roster_id,
            opponent_roster_id=None,
            my_projected=0.0,
            opponent_projected=0.0,
            win_probability=0.5,
            lineup_upside=0.0,
            recommended_swaps=[],
            note="No head-to-head this week; check back in season.",
            warnings=warnings,
        )

    my_mean = _team_strength(
        roster_by_id[my_roster_id], players, per_game_fp, CURRENT_LEAGUE_YEAR, week
    )
    opp_mean = _team_strength(roster_by_id[opp_id], players, per_game_fp, CURRENT_LEAGUE_YEAR, week)
    my_std = max(_STD_FLOOR, _STD_FRACTION * my_mean)
    opp_std = max(_STD_FLOOR, _STD_FRACTION * opp_mean)
    wp = win_probability(my_mean, opp_mean, my_std, opp_std)

    upside = 0.0
    swaps: list[dict] = []
    try:
        from sleeper_ffm.season.startsit import build_startsit

        ss = build_startsit(week, DEFAULT_VALUE_SEASON)
        upside = round(ss.total_projected_pts - ss.current_projected_pts, 1)
        swaps = ss.changes[:5]
    except Exception as exc:
        log.info("gameday: start/sit upside unavailable: %s", exc)
        warnings.append("Start/sit optimizer unavailable; lineup upside omitted.")

    return GamedayBrief(
        week=week,
        season=DEFAULT_VALUE_SEASON,
        has_matchup=True,
        my_roster_id=my_roster_id,
        opponent_roster_id=opp_id,
        my_projected=round(my_mean, 1),
        opponent_projected=round(opp_mean, 1),
        win_probability=wp,
        lineup_upside=upside,
        recommended_swaps=swaps,
        note=f"Win probability {wp:.0%} vs roster {opp_id} as lineups stand.",
        warnings=warnings,
    )
