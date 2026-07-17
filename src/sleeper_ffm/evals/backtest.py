"""Out-of-sample backtest for the red-zone-opportunity expected-TD model.

The regression engine claims its red-zone-opportunity TD model beats the flat
yardage baseline. This module *measures* that claim reproducibly rather than
asserting it in a docstring: fit each model on ``train_season`` and score it on
``eval_season`` (a season it never saw), then compare mean-absolute expected-TD
error against actual touchdowns.

The two expected-TD models under test (both from :mod:`sleeper_ffm.model.regression`):
    * **yardage** — position TD-per-yard rate (trained on ``train_season``) times a
      player's ``eval_season`` yardage.
    * **redzone-opportunity** — each red-zone / non-red-zone target and carry priced
      by its trained (``train_season``) touchdown probability, applied to the player's
      ``eval_season`` opportunity counts.

Everything reads from the on-disk nflverse parquet cache (no live fetch); a season
with no cached play-by-play yields an unavailable result rather than an error.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

from sleeper_ffm.model.regression import _aggregate_rows, compute_td_regression
from sleeper_ffm.model.valuation import SKILL_POSITIONS
from sleeper_ffm.nflverse.loader import load_id_map, load_pbp
from sleeper_ffm.scoring.engine import load_scoring

log = logging.getLogger(__name__)

_MIN_YARDS = 250


class BacktestUnavailableError(RuntimeError):
    """Raised when the cached data needed to run the backtest is missing."""


@dataclass
class BacktestResult:
    """Out-of-sample expected-TD accuracy for both models on one train→eval split."""

    train_season: int
    eval_season: int
    n_players: int
    mae_redzone: float
    mae_yardage: float
    improvement_pct: float  # (mae_yardage - mae_redzone) / mae_yardage, as a percentage


def _play_values(season: int) -> pl.DataFrame:
    """Play-level FP/TD values for a season, or empty if PBP isn't cached."""
    from sleeper_ffm.model.sabermetrics import pbp_play_value

    pbp = load_pbp(seasons=[season])
    if pbp.is_empty():
        return pbp
    return pbp_play_value(pbp, load_scoring())


def _position_by_player() -> dict[str, str]:
    """gsis_id → position from the nflverse ID crosswalk, skill positions only."""
    id_map = load_id_map()
    out: dict[str, str] = {}
    for r in id_map.select(["gsis_id", "position"]).iter_rows(named=True):
        gsis, pos = r.get("gsis_id"), r.get("position")
        if gsis and pos in SKILL_POSITIONS:
            out[gsis] = pos
    return out


def run_redzone_backtest(
    train_season: int,
    eval_season: int,
    min_yards: int = _MIN_YARDS,
) -> BacktestResult:
    """Measure out-of-sample expected-TD MAE for both models on one train→eval split.

    Args:
        train_season: Season the TD rates / yardage baselines are fit on.
        eval_season: Held-out season the fitted models are scored against.
        min_yards: Minimum eval-season yardage for a player to enter the sample
            (the same low-sample noise guard the live engine uses).

    Returns:
        A :class:`BacktestResult` with both models' MAE and the relative improvement.

    Raises:
        BacktestUnavailableError: If either season lacks cached play-by-play, or no
            player clears ``min_yards`` in the eval season.
    """
    from sleeper_ffm.model.sabermetrics import player_redzone_opportunities, redzone_td_rates

    train_rows = _aggregate_rows(train_season)
    eval_rows = _aggregate_rows(eval_season)
    if not train_rows or not eval_rows:
        raise BacktestUnavailableError(f"weekly stats missing for {train_season} or {eval_season}")

    train_plays = _play_values(train_season)
    eval_plays = _play_values(eval_season)
    if train_plays.is_empty() or eval_plays.is_empty():
        raise BacktestUnavailableError(f"play-by-play missing for {train_season} or {eval_season}")

    pos_map = _position_by_player()

    # Fit both models on the train season only.
    trained_rates = redzone_td_rates(train_plays, pos_map)
    yardage_baselines, _ = compute_td_regression(train_rows, min_yards=min_yards)

    abs_err_rz: list[float] = []
    abs_err_yd: list[float] = []
    for r in eval_rows:
        pos = r["position"]
        gsis = r.get("gsis_id")
        if r["total_yards"] < min_yards or not gsis:
            continue
        pos_rates = trained_rates.get(pos)
        yd_rate = yardage_baselines.get(pos)
        if pos_rates is None or yd_rate is None:
            continue

        actual = r["total_tds"]
        opps = player_redzone_opportunities(eval_plays, gsis)
        expected_rz = sum(opps.get(k, 0.0) * pos_rates.get(k, 0.0) for k in opps)
        expected_yd = r["total_yards"] * yd_rate
        abs_err_rz.append(abs(actual - expected_rz))
        abs_err_yd.append(abs(actual - expected_yd))

    n = len(abs_err_rz)
    if n == 0:
        raise BacktestUnavailableError(f"no players cleared {min_yards} yards in {eval_season}")

    mae_rz = sum(abs_err_rz) / n
    mae_yd = sum(abs_err_yd) / n
    improvement = ((mae_yd - mae_rz) / mae_yd * 100.0) if mae_yd else 0.0
    return BacktestResult(
        train_season=train_season,
        eval_season=eval_season,
        n_players=n,
        mae_redzone=round(mae_rz, 4),
        mae_yardage=round(mae_yd, 4),
        improvement_pct=round(improvement, 2),
    )
