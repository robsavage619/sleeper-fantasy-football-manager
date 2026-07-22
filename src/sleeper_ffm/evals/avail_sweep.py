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
from collections.abc import Callable
from dataclasses import dataclass

from sleeper_ffm.evals.arena import (
    _DEFAULT_MAX_WEEK,
    _DEFAULT_MIN_WEEK,
    _DNP_FACTOR,
    _QUESTIONABLE_FACTOR,
    ArenaUnavailableError,
    PointHistory,
    Projector,
    WeekScore,
    _extend_history,
    _player_positions,
    _replay_week,
    _resolve_league_id,
    make_engine_projector,
)

log = logging.getLogger(__name__)

_BASELINE = (_QUESTIONABLE_FACTOR, _DNP_FACTOR)

# A variant projector built per season, sharing one forecast cache across variants.
ProjectorFactory = Callable[[int, dict[tuple[str, int], float]], Projector]


def _replay_factories(
    seasons: tuple[int, ...],
    factories: dict[str, ProjectorFactory],
    min_week: int,
    max_week: int,
) -> dict[str, list[WeekScore]]:
    """Replay every season once per variant, fetching matchups and forecasts only once.

    All variants see the identical roster-weeks in the identical order, so their
    ``WeekScore`` lists are pairable element-wise for bootstrap comparisons.
    """
    from sleeper_ffm.sleeper.client import SleeperClient

    scores: dict[str, list[WeekScore]] = {name: [] for name in factories}
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
        for name, factory in factories.items():
            projector = factory(season, forecast_cache)
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
                            scores[name].append(score)
                _extend_history(history, matchups)
        log.info("avail_sweep: season %s replayed (%d variants)", season, len(factories))
    return scores


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
    cells = [(q, d) for q in q_factors for d in dnp_factors]
    if _BASELINE not in cells:
        cells.append(_BASELINE)

    def cell_factory(q: float, d: float) -> ProjectorFactory:
        return lambda season, cache: make_engine_projector(
            season, questionable_factor=q, dnp_factor=d, forecast_cache=cache
        )

    factories = {f"{q}|{d}": cell_factory(q, d) for q, d in cells}
    scores = _replay_factories(seasons, factories, min_week, max_week)
    base_key = f"{_BASELINE[0]}|{_BASELINE[1]}"
    if not scores[base_key]:
        raise ArenaUnavailableError(f"no scorable roster-weeks in seasons {seasons}")

    out = [_summarize_cell(q, d, scores[f"{q}|{d}"], scores[base_key]) for q, d in cells]
    out.sort(key=lambda c: -c.engine_capture)
    return out


def _summarize_cell(
    q: float, d: float, scores: list[WeekScore], base: list[WeekScore]
) -> SweepCell:
    from sleeper_ffm.evals.stats import paired_diff_ci

    series = [s.engine_pts for s in scores]
    base_series = [s.engine_pts for s in base]
    optimal_total = sum(s.optimal_pts for s in scores)
    n = len(scores)
    return SweepCell(
        questionable_factor=q,
        dnp_factor=d,
        n_roster_weeks=n,
        engine_capture=sum(series) / optimal_total if optimal_total else 0.0,
        dead_per_week=sum(s.engine_zero_starters for s in scores) / n if n else 0.0,
        margin_vs_base=round((sum(series) - sum(base_series)) / n if n else 0.0, 3),
        margin_ci=paired_diff_ci(series, base_series),
    )


@dataclass
class PracticeCompare:
    """Practice-conditioned availability (Lever F) vs the shipped flat constants."""

    seasons: tuple[int, ...]
    n_roster_weeks: int
    base_capture: float
    practice_capture: float
    base_dead: float
    practice_dead: float
    margin: float
    margin_ci: tuple[float, float]
    weeks_changed: int
    outscore_pvalue: float

    def summary(self) -> str:
        """One-line verdict."""
        lo, hi = self.margin_ci
        return (
            f"{list(self.seasons)}: practice-conditioned capture "
            f"{self.practice_capture:.2%} vs base {self.base_capture:.2%} "
            f"({self.n_roster_weeks} roster-weeks, lineups changed {self.weeks_changed}x); "
            f"dead starters {self.practice_dead:.2f}/wk vs {self.base_dead:.2f}; "
            f"{self.margin:+.2f} pts/wk [95% CI {lo:+.2f}, {hi:+.2f}], "
            f"p={self.outscore_pvalue}"
        )


def run_practice_compare(
    seasons: tuple[int, ...],
    min_week: int = _DEFAULT_MIN_WEEK,
    max_week: int = _DEFAULT_MAX_WEEK,
) -> PracticeCompare:
    """Paired replay: Lever F (practice-conditioned shades) on vs off, same roster-weeks.

    Raises:
        ArenaUnavailableError: A season's league history or matchups could not be loaded.
    """
    from sleeper_ffm.evals.stats import paired_diff_ci, sign_test_pvalue

    factories: dict[str, ProjectorFactory] = {
        "base": lambda season, cache: make_engine_projector(
            season, use_practice=False, forecast_cache=cache
        ),
        "practice": lambda season, cache: make_engine_projector(
            season, use_practice=True, forecast_cache=cache
        ),
    }
    scores = _replay_factories(seasons, factories, min_week, max_week)
    base, prac = scores["base"], scores["practice"]
    if not base:
        raise ArenaUnavailableError(f"no scorable roster-weeks in seasons {seasons}")

    base_series = [s.engine_pts for s in base]
    prac_series = [s.engine_pts for s in prac]
    n = len(base)
    diffs = [p - b for p, b in zip(prac_series, base_series, strict=True)]
    changed = sum(1 for d in diffs if abs(d) > 1e-9)
    wins = sum(1 for d in diffs if d > 1e-9)
    return PracticeCompare(
        seasons=seasons,
        n_roster_weeks=n,
        base_capture=sum(base_series) / sum(s.optimal_pts for s in base),
        practice_capture=sum(prac_series) / sum(s.optimal_pts for s in prac),
        base_dead=sum(s.engine_zero_starters for s in base) / n,
        practice_dead=sum(s.engine_zero_starters for s in prac) / n,
        margin=round(sum(diffs) / n, 3),
        margin_ci=paired_diff_ci(prac_series, base_series),
        weeks_changed=changed,
        outscore_pvalue=sign_test_pvalue(wins, changed),
    )


__all__ = ["PracticeCompare", "SweepCell", "run_avail_sweep", "run_practice_compare"]
