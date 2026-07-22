"""Win-probability lineup selection — trade mean points for weekly wins, measured.

The arena ranks lineups on the projected mean, which is the right policy for maximizing
capture — and the gap decomposition shows the engine already ranks healthy players at
manager parity. But fantasy is head-to-head: an underdog should prefer a higher-variance
lineup even at a small cost in mean, and a favorite should protect its floor. This module
tests that decision-theoretic layer in the same blind replay as the arena.

Mechanism, all point-in-time:

* Every roster's players are projected by the same blind projector the arena uses.
* Each roster's *opponent* (shared ``matchup_id``) gets a projected total distribution:
  the mean-optimal lineup's summed means, variance from per-player stds — each player's
  own game-log CV shrunk toward his position's CV, both measured on the league's own
  prior-week logs (:func:`position_cvs` / :func:`player_stds` — self-contained,
  leak-free). Player-level dispersion is what lets a boom-bust candidate beat a steady
  one of similar mean; position-pooled CVs alone make same-position swaps impossible.
* The win-prob selector starts from the mean-optimal lineup and greedily applies the
  single legal swap that most raises ``P(my_total > opp_total)`` (normal approximation),
  sacrificing at most :data:`_MAX_SACRIFICE` projected points per swap, up to
  :data:`_MAX_SWAPS` swaps. As a favorite that surfaces floor-protecting swaps, as an
  underdog variance-seeking ones — no special-casing, the objective handles both.
* Both lineups (mean-optimal and win-prob) are then scored on realized points against the
  opponent's actual posted total, exactly like ``run_h2h``. The interesting weeks are the
  ones where the two selectors disagree.

The harness also reports calibration (Brier score of predicted win prob vs realized
outcome): if the projected distributions are junk, that shows up here before any
conclusion about the selector is trusted.
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field

from sleeper_ffm.evals.arena import (
    _DEDICATED,
    _DEFAULT_MAX_WEEK,
    _DEFAULT_MIN_WEEK,
    ArenaUnavailableError,
    PointHistory,
    Projector,
    _extend_history,
    _player_positions,
    _resolve_league_id,
    make_engine_projector,
    select_lineup,
)
from sleeper_ffm.model.owner_skill import _FLEX_ELIGIBLE, _NON_STARTING_SLOTS

log = logging.getLogger(__name__)

# A swap may cost at most this many projected points — beyond that the mean sacrifice
# outweighs any plausible variance gain in a ~120-point lineup.
_MAX_SACRIFICE = 3.0
_MAX_SWAPS = 3

# Per-position game-to-game CV fallbacks for early weeks with too little league history.
# Overridden by measured in-season values as soon as the sample supports them.
_DEFAULT_CVS = {"QB": 0.45, "RB": 0.65, "WR": 0.75, "TE": 0.85, "K": 0.55, "DEF": 0.80}
_MIN_GAMES_FOR_CV = 4
_MIN_MEAN_FOR_CV = 3.0
# Empirical-Bayes weight pulling a player's own CV toward his position's: a 4-game log
# counts as much as the positional prior, a 14-game log mostly speaks for itself.
_CV_SHRINK_K = 4.0


def position_cvs(history: PointHistory, positions: dict[str, str]) -> dict[str, float]:
    """Per-position coefficient of variation from the league's own prior-week game logs.

    Median CV over players with enough games and a non-trivial mean; positions without a
    usable sample fall back to :data:`_DEFAULT_CVS`. Uses only ``history``, so it is
    exactly as blind as any projector.
    """
    samples: dict[str, list[float]] = {}
    for pid, games in history.by_player.items():
        pos = positions.get(pid)
        if pos not in _DEFAULT_CVS or len(games) < _MIN_GAMES_FOR_CV:
            continue
        mean = statistics.mean(games)
        if mean < _MIN_MEAN_FOR_CV:
            continue
        samples.setdefault(pos, []).append(statistics.stdev(games) / mean)
    out = dict(_DEFAULT_CVS)
    for pos, cvs in samples.items():
        if len(cvs) >= 3:
            out[pos] = statistics.median(cvs)
    return out


def player_stds(
    means: dict[str, float],
    history: PointHistory,
    positions: dict[str, str],
    pos_cvs: dict[str, float],
) -> dict[str, float]:
    """Per-player projected std: own game-log CV shrunk toward the position CV.

    Position-pooled CVs make std proportional to mean within a position, which blinds the
    win-prob selector to the boom-bust-vs-steady distinction that makes same-position
    variance swaps possible at all. A player's own dispersion, empirical-Bayes shrunk
    (weight :data:`_CV_SHRINK_K`), restores it — still built only from blind ``history``.
    """
    out: dict[str, float] = {}
    for pid, mean in means.items():
        pos_cv = pos_cvs.get(positions.get(pid, ""), 0.7)
        games = history.by_player.get(pid) or []
        own_mean = statistics.mean(games) if games else 0.0
        if len(games) >= _MIN_GAMES_FOR_CV and own_mean >= _MIN_MEAN_FOR_CV:
            own_cv = statistics.stdev(games) / own_mean
            n = float(len(games))
            cv = (n * own_cv + _CV_SHRINK_K * pos_cv) / (n + _CV_SHRINK_K)
        else:
            cv = pos_cv
        out[pid] = cv * mean
    return out


def assign_lineup(
    scores: dict[str, float],
    positions: dict[str, str],
    roster_positions: list[str],
) -> list[tuple[str, str]]:
    """Slot-aware version of :func:`select_lineup`: ``[(slot, player_id), ...]``.

    Same greedy fill, same chosen players — but the slot each starter occupies is kept so
    swap legality (dedicated slot vs FLEX) can be checked.
    """
    pools: dict[str, list[str]] = {pos: [] for pos in _DEDICATED}
    for pid in scores:
        pos = positions.get(pid)
        if pos in pools:
            pools[pos].append(pid)
    for pos in pools:
        pools[pos].sort(key=lambda p: scores.get(p, 0.0), reverse=True)

    chosen: list[tuple[str, str]] = []
    flex_slots = 0
    for slot in roster_positions:
        if slot in _NON_STARTING_SLOTS:
            continue
        if slot == "FLEX":
            flex_slots += 1
            continue
        if pools.get(slot):
            chosen.append((slot, pools[slot].pop(0)))

    if flex_slots:
        flex_pool = sorted(
            (pid for pos in _FLEX_ELIGIBLE for pid in pools.get(pos, [])),
            key=lambda p: scores.get(p, 0.0),
            reverse=True,
        )
        chosen.extend(("FLEX", pid) for pid in flex_pool[:flex_slots])
    return chosen


def win_probability(my_mean: float, my_var: float, opp_mean: float, opp_var: float) -> float:
    """``P(my_total > opp_total)`` under independent normal totals."""
    spread = math.sqrt(my_var + opp_var)
    if spread <= 0:
        return 1.0 if my_mean > opp_mean else 0.0 if my_mean < opp_mean else 0.5
    return 0.5 * (1.0 + math.erf((my_mean - opp_mean) / (spread * math.sqrt(2.0))))


def select_winprob_lineup(
    means: dict[str, float],
    stds: dict[str, float],
    positions: dict[str, str],
    roster_positions: list[str],
    opp_mean: float,
    opp_var: float,
    max_sacrifice: float = _MAX_SACRIFICE,
    max_swaps: int = _MAX_SWAPS,
) -> tuple[list[str], float]:
    """Pick the lineup maximizing win probability; returns ``(player_ids, p_win)``.

    Starts from the mean-optimal lineup and greedily applies the best legal single swap
    (same slot: identical position for dedicated slots, any FLEX-eligible position for
    FLEX) that raises ``P(win)``, each costing at most ``max_sacrifice`` projected points.
    """

    def std(pid: str) -> float:
        return stds.get(pid, 0.7 * means.get(pid, 0.0))

    assignment = assign_lineup(means, positions, roster_positions)
    started = {pid for _, pid in assignment}
    bench = [pid for pid in means if pid not in started]

    my_mean = sum(means.get(pid, 0.0) for _, pid in assignment)
    my_var = sum(std(pid) ** 2 for _, pid in assignment)
    best_p = win_probability(my_mean, my_var, opp_mean, opp_var)

    for _ in range(max_swaps):
        best_swap: tuple[int, str, float] | None = None  # (slot index, bench pid, new p)
        for i, (slot, out_pid) in enumerate(assignment):
            for in_pid in bench:
                pos = positions.get(in_pid)
                legal = pos == slot if slot != "FLEX" else pos in _FLEX_ELIGIBLE
                if not legal:
                    continue
                if means.get(out_pid, 0.0) - means.get(in_pid, 0.0) > max_sacrifice:
                    continue
                new_mean = my_mean - means.get(out_pid, 0.0) + means.get(in_pid, 0.0)
                new_var = my_var - std(out_pid) ** 2 + std(in_pid) ** 2
                p = win_probability(new_mean, new_var, opp_mean, opp_var)
                if p > best_p + 1e-9 and (best_swap is None or p > best_swap[2]):
                    best_swap = (i, in_pid, p)
        if best_swap is None:
            break
        i, in_pid, best_p = best_swap
        slot, out_pid = assignment[i]
        assignment[i] = (slot, in_pid)
        bench.remove(in_pid)
        bench.append(out_pid)
        my_mean = sum(means.get(pid, 0.0) for _, pid in assignment)
        my_var = sum(std(pid) ** 2 for _, pid in assignment)

    return [pid for _, pid in assignment], best_p


@dataclass
class WinProbLeagueResult:
    """Mean-selector vs win-prob-selector, every roster, one season, same blind replay."""

    season: int
    league_id: str
    n_roster_weeks: int
    # Head-to-head wins vs the real opponent's actual total, summed over all rosters.
    mean_wins: int
    winprob_wins: int
    # Weeks where the two selectors chose different lineups, and the flips among them.
    differing_weeks: int
    flips_gained: int  # winprob won a week the mean lineup lost
    flips_lost: int  # winprob lost a week the mean lineup won
    # Mean engine points per roster-week for each selector — the capture-cost check.
    mean_pts: float
    winprob_pts: float
    # Calibration of the predicted win probability against realized outcomes.
    brier: float
    brier_base: float  # always-0.5 baseline
    flip_pvalue: float = 1.0
    calibration: list[tuple[float, float, int]] = field(default_factory=list)

    def summary(self) -> str:
        """One-line verdict plus the calibration table."""
        lines = [
            f"{self.season}: winprob {self.winprob_wins} H2H wins vs mean-selector "
            f"{self.mean_wins} ({self.n_roster_weeks} roster-weeks); "
            f"lineups differed {self.differing_weeks}x, flips +{self.flips_gained}/"
            f"-{self.flips_lost} (p={self.flip_pvalue}); "
            f"pts/wk {self.winprob_pts:.1f} vs {self.mean_pts:.1f}; "
            f"Brier {self.brier:.4f} vs coin-flip {self.brier_base:.4f}"
        ]
        for lo, rate, n in self.calibration:
            lines.append(f"  predicted ~{lo:.0%}: won {rate:.0%} of {n}")
        return "\n".join(lines)


def run_winprob_league(
    season: int,
    projector: Projector | None = None,
    min_week: int = _DEFAULT_MIN_WEEK,
    max_week: int = _DEFAULT_MAX_WEEK,
    league_id: str | None = None,
) -> WinProbLeagueResult:
    """Replay every roster with both selectors and count who wins more real matchups.

    Single pass: each week every roster is projected once, giving both its mean-optimal
    lineup and the opponent-total distribution the win-prob selector needs. The opponent's
    *actual* posted total is the bar, as in ``run_h2h``.

    Raises:
        ArenaUnavailableError: League history or matchups unavailable.
    """
    from sleeper_ffm.evals.stats import sign_test_pvalue
    from sleeper_ffm.sleeper.client import SleeperClient

    with SleeperClient() as client:
        lid = league_id or _resolve_league_id(client, season)
        if lid is None:
            raise ArenaUnavailableError(f"no league in this dynasty's history for {season}")
        league = client.league(lid)
        roster_positions = list(league.roster_positions or [])
        if not roster_positions:
            raise ArenaUnavailableError(f"league {lid} has no roster_positions")
        regular_weeks = min(int(league.settings.get("playoff_week_start", 15)) - 1, max_week)
        positions = _player_positions(client)
        proj = projector or make_engine_projector(season)

        history = PointHistory()
        n = mean_wins = winprob_wins = differing = gained = lost = 0
        mean_pts_total = winprob_pts_total = 0.0
        predictions: list[tuple[float, bool]] = []

        for week in range(1, regular_weeks + 1):
            try:
                matchups = client.matchups(week, league_id=lid)
            except Exception as exc:
                log.warning("winprob: %s week %s unavailable: %s", season, week, exc)
                matchups = []
            if not matchups:
                continue

            if week >= min_week:
                cvs = position_cvs(history, positions)
                by_roster = {int(r.get("roster_id", -1)): r for r in matchups}

                # Blind projections and mean-optimal distributions, one pass per roster.
                projections: dict[int, dict[str, float]] = {}
                stds_by_roster: dict[int, dict[str, float]] = {}
                dists: dict[int, tuple[float, float]] = {}
                for rid, roster in by_roster.items():
                    available = [pid for pid in (roster.get("players") or []) if pid]
                    if not available or not roster.get("players_points"):
                        continue
                    means = proj(week, available, positions, history)
                    stds = player_stds(means, history, positions, cvs)
                    projections[rid] = means
                    stds_by_roster[rid] = stds
                    lineup = select_lineup(means, positions, roster_positions)
                    mu = sum(means.get(pid, 0.0) for pid in lineup)
                    var = sum(stds.get(pid, 0.0) ** 2 for pid in lineup)
                    dists[rid] = (mu, var)

                for rid, roster in by_roster.items():
                    if rid not in projections:
                        continue
                    opp = next(
                        (
                            r
                            for orid, r in by_roster.items()
                            if orid != rid and r.get("matchup_id") == roster.get("matchup_id")
                        ),
                        None,
                    )
                    if opp is None or roster.get("matchup_id") is None:
                        continue
                    opp_rid = int(opp.get("roster_id", -1))
                    if opp_rid not in dists:
                        continue
                    opp_mean, opp_var = dists[opp_rid]
                    opp_actual = float(opp.get("points") or 0.0)
                    actual_points = {
                        pid: float(p) for pid, p in (roster.get("players_points") or {}).items()
                    }
                    means = projections[rid]

                    mean_ids = select_lineup(means, positions, roster_positions)
                    wp_ids, p_win = select_winprob_lineup(
                        means,
                        stds_by_roster[rid],
                        positions,
                        roster_positions,
                        opp_mean,
                        opp_var,
                    )
                    mean_score = sum(actual_points.get(pid, 0.0) for pid in mean_ids)
                    wp_score = sum(actual_points.get(pid, 0.0) for pid in wp_ids)

                    n += 1
                    mean_pts_total += mean_score
                    winprob_pts_total += wp_score
                    mean_won = mean_score > opp_actual
                    wp_won = wp_score > opp_actual
                    mean_wins += mean_won
                    winprob_wins += wp_won
                    if set(mean_ids) != set(wp_ids):
                        differing += 1
                        gained += wp_won and not mean_won
                        lost += mean_won and not wp_won
                    predictions.append((p_win, wp_won))

            _extend_history(history, matchups)

    if not n:
        raise ArenaUnavailableError(f"no scorable roster-weeks for season {season}")

    brier = statistics.mean((p - float(won)) ** 2 for p, won in predictions)
    brier_base = statistics.mean((0.5 - float(won)) ** 2 for p, won in predictions)
    return WinProbLeagueResult(
        season=season,
        league_id=lid,
        n_roster_weeks=n,
        mean_wins=mean_wins,
        winprob_wins=winprob_wins,
        differing_weeks=differing,
        flips_gained=gained,
        flips_lost=lost,
        mean_pts=round(mean_pts_total / n, 2),
        winprob_pts=round(winprob_pts_total / n, 2),
        brier=round(brier, 4),
        brier_base=round(brier_base, 4),
        flip_pvalue=sign_test_pvalue(gained, gained + lost),
        calibration=_calibration_buckets(predictions),
    )


def _calibration_buckets(
    predictions: list[tuple[float, bool]], width: float = 0.2
) -> list[tuple[float, float, int]]:
    """``(bucket_low, realized_win_rate, n)`` rows over predicted-probability buckets."""
    out: list[tuple[float, float, int]] = []
    lo = 0.0
    while lo < 1.0:
        hits = [won for p, won in predictions if lo <= p < lo + width]
        if hits:
            out.append((lo, sum(hits) / len(hits), len(hits)))
        lo = round(lo + width, 10)
    return out


__all__ = [
    "WinProbLeagueResult",
    "assign_lineup",
    "player_stds",
    "position_cvs",
    "run_winprob_league",
    "select_winprob_lineup",
    "win_probability",
]
