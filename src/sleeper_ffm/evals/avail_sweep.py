"""Availability-constant sweep — tune Levers A/B against the arena, not by intuition.

The gap decomposition (:mod:`sleeper_ffm.evals.gap_report`) showed ~2.4pp of the ~2.6pp
manager gap is availability, split almost evenly between starting dead players
(``dead_starter``) and over-benching flagged players who went on to produce
(``benched_flagged``). Those two buckets trade off directly through the two shade
constants — a softer Questionable/DNP discount starts more producers but also more
scratches — so the right setting is an empirical question the arena can answer.

This sweep replays a season once per ``(questionable_factor, dnp_factor)`` cell, sharing
the forecast cache and the fetched matchups across cells so the grid costs little more
than a single arena run. Every cell is scored on the same roster-weeks, so cells are
compared with a paired bootstrap CI against the shipped baseline (0.8, 0.3).

Overfit discipline: pick constants on the fit seasons (2022-2023), then confirm the
chosen cell on a held-out season (2024) before promoting anything.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sleeper_ffm.evals.arena import (
    _DEFAULT_MAX_WEEK,
    _DEFAULT_MIN_WEEK,
    _DNP_FACTOR,
    _QUESTIONABLE_FACTOR,
    ArenaUnavailableError,
    PointHistory,
    WeekScore,
    _extend_history,
    _player_positions,
    _replay_week,
    _resolve_league_id,
    make_engine_projector,
)

log = logging.getLogger(__name__)

_BASELINE = (_QUESTIONABLE_FACTOR, _DNP_FACTOR)


@dataclass
class SweepCell:
    """Pooled arena outcome for one ``(questionable_factor, dnp_factor)`` setting."""

    questionable_factor: float
    dnp_factor: float
    n_roster_weeks: int
    engine_capture: float
    dead_per_week: float
    # Mean pts/wk vs the shipped (0.8, 0.3) baseline on the same roster-weeks, with CI.
    margin_vs_base: float
    margin_ci: tuple[float, float]

    def row(self) -> str:
        """One grid row for the CLI table."""
        lo, hi = self.margin_ci
        base = " (baseline)" if (self.questionable_factor, self.dnp_factor) == _BASELINE else ""
        return (
            f"q={self.questionable_factor:.2f} dnp={self.dnp_factor:.2f}: "
            f"capture {self.engine_capture:.2%}, dead {self.dead_per_week:.2f}/wk, "
            f"{self.margin_vs_base:+.2f} pts/wk vs base [95% CI {lo:+.2f}, {hi:+.2f}]{base}"
        )


def run_avail_sweep(
    seasons: tuple[int, ...],
    q_factors: tuple[float, ...],
    dnp_factors: tuple[float, ...],
    min_week: int = _DEFAULT_MIN_WEEK,
    max_week: int = _DEFAULT_MAX_WEEK,
) -> list[SweepCell]:
    """Sweep the availability constants over pooled seasons, paired against baseline.

    The baseline cell (0.8, 0.3) is always included even if absent from the grid, since
    every cell's margin is computed against it.

    Raises:
        ArenaUnavailableError: A season's league history or matchups could not be loaded.
    """
    from sleeper_ffm.evals.stats import paired_diff_ci
    from sleeper_ffm.sleeper.client import SleeperClient

    cells = [(q, d) for q in q_factors for d in dnp_factors]
    if _BASELINE not in cells:
        cells.append(_BASELINE)

    scores_by_cell: dict[tuple[float, float], list[WeekScore]] = {c: [] for c in cells}
    for season in seasons:
        with SleeperClient() as client:
            lid = _resolve_league_id(client, season)
            if lid is None:
                raise ArenaUnavailableError(f"no league in this dynasty's history for {season}")
            league = client.league(lid)
            roster_positions = list(league.roster_positions or [])
            if not roster_positions:
                raise ArenaUnavailableError(f"league {lid} has no roster_positions")
            positions = _player_positions(client)
            matchups_by_week: dict[int, list[dict]] = {}
            for week in range(1, max_week + 1):
                try:
                    matchups_by_week[week] = client.matchups(week, league_id=lid)
                except Exception as exc:
                    log.warning("avail_sweep: %s week %s unavailable: %s", season, week, exc)
                    matchups_by_week[week] = []

        forecast_cache: dict[tuple[str, int], float] = {}
        for q, d in cells:
            projector = make_engine_projector(
                season, questionable_factor=q, dnp_factor=d, forecast_cache=forecast_cache
            )
            history = PointHistory()
            for week in range(1, max_week + 1):
                matchups = matchups_by_week[week]
                if not matchups:
                    continue
                if week >= min_week:
                    for roster in matchups:
                        score = _replay_week(
                            week, roster, positions, roster_positions, history, projector
                        )
                        if score is not None:
                            scores_by_cell[(q, d)].append(score)
                _extend_history(history, matchups)
        log.info("avail_sweep: season %s swept (%d cells)", season, len(cells))

    base_scores = scores_by_cell[_BASELINE]
    if not base_scores:
        raise ArenaUnavailableError(f"no scorable roster-weeks in seasons {seasons}")
    base_series = [s.engine_pts for s in base_scores]

    out: list[SweepCell] = []
    for cell, scores in scores_by_cell.items():
        series = [s.engine_pts for s in scores]
        optimal_total = sum(s.optimal_pts for s in scores)
        margins_ci = paired_diff_ci(series, base_series)
        n = len(scores)
        out.append(
            SweepCell(
                questionable_factor=cell[0],
                dnp_factor=cell[1],
                n_roster_weeks=n,
                engine_capture=sum(series) / optimal_total if optimal_total else 0.0,
                dead_per_week=sum(s.engine_zero_starters for s in scores) / n if n else 0.0,
                margin_vs_base=round(
                    (sum(series) - sum(base_series)) / n if n else 0.0,
                    3,
                ),
                margin_ci=margins_ci,
            )
        )
    out.sort(key=lambda c: -c.engine_capture)
    return out


__all__ = ["SweepCell", "run_avail_sweep"]
