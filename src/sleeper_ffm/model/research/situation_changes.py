"""S2 — does production follow the player or the situation?

The question this study exists to answer is the one that decides how to value a
player who just changed teams: when a receiver moves, does he take his role with
him, or does he inherit whatever the new offense hands him?

The design is a natural experiment. Every season, roughly a quarter of returning
players change teams and half play with a different primary quarterback (measured
in :mod:`sleeper_ffm.model.context_table`). Those who stay put are the control
group. If prior usage predicts current usage just as well for movers as for
stayers, the player carries his role; if the relationship decays for movers, the
situation is doing the work.

The same comparison runs against three separate disruptions — a new team, a new
play-caller, a new quarterback — because they are not the same event and the
engine currently treats all three as invisible.

Everything here is measured on usage *share* rather than raw volume. Volume
confounds the question: a player on a pass-heavy team gets more targets without
being more central to his offense. Share is the closest available reading of
"how much of this offense runs through him", which is the thing that either
travels or does not.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import polars as pl

from sleeper_ffm.model.context_table import load_context_table

log = logging.getLogger(__name__)

# Below this the share estimates are too noisy to compare across situations.
MIN_GAMES = 8

# Disruptions tested, mapped to the context-table flag that marks them.
CHANGE_FLAGS = ("team_changed", "coach_changed", "qb_changed")

# Usage measures. Receiving share is the cleanest signal for pass catchers;
# carry share carries the running-back question.
USAGE_METRICS = ("target_share", "air_yards_share", "wopr")


@dataclass(frozen=True)
class CarryoverResult:
    """How well prior-season usage predicts current usage, for one group.

    Attributes:
        metric: Usage measure tested.
        change: Which disruption defines the group (or ``none`` for the control).
        position: Position group, or ``ALL``.
        group: ``changed`` or ``stable``.
        n: Player-seasons behind the estimate.
        correlation: Pearson r between prior-season and current-season usage.
    """

    metric: str
    change: str
    position: str
    group: str
    n: int
    correlation: float


def _pearson(xs: list[float | None], ys: list[float | None]) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys, strict=True) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return float("nan")
    mean_x = sum(p[0] for p in pairs) / n
    mean_y = sum(p[1] for p in pairs) / n
    sx = math.sqrt(sum((p[0] - mean_x) ** 2 for p in pairs))
    sy = math.sqrt(sum((p[1] - mean_y) ** 2 for p in pairs))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((p[0] - mean_x) * (p[1] - mean_y) for p in pairs) / (sx * sy)


def eligible_pairs(seasons: list[int] | None = None) -> pl.DataFrame:
    """Load context rows that have both a prior and a current season worth comparing.

    Args:
        seasons: Restrict to these seasons. Defaults to the whole table.

    Returns:
        Context-table rows with a known prior team and enough games at both ends.
    """
    df = load_context_table()
    if df.is_empty():
        log.warning("situation_changes: context table empty")
        return df
    if seasons is not None:
        df = df.filter(pl.col("season").is_in(seasons))
    return df.filter(
        pl.col("prior_team").is_not_null()
        & pl.col("games").ge(MIN_GAMES)
        & pl.col("prior_games").ge(MIN_GAMES)
    )


def usage_carryover(
    seasons: list[int] | None = None,
    positions: tuple[str, ...] = ("WR", "TE", "RB"),
) -> list[CarryoverResult]:
    """Compare prior-to-current usage persistence for changed vs stable players.

    For each disruption and usage metric, correlates a player's prior-season usage
    share with his current one, separately for players who experienced the
    disruption and those who did not. The gap between the two correlations is the
    estimate of how much the situation overrides the player.

    Args:
        seasons: Seasons to include. Defaults to the whole table.
        positions: Positions to report individually alongside the pooled result.

    Returns:
        One result per (metric, disruption, position, group).
    """
    df = eligible_pairs(seasons)
    if df.is_empty():
        return []

    results: list[CarryoverResult] = []
    for metric in USAGE_METRICS:
        prior_col = f"prior_{metric}"
        if metric not in df.columns or prior_col not in df.columns:
            continue
        for flag in CHANGE_FLAGS:
            for position in ("ALL", *positions):
                sub = df if position == "ALL" else df.filter(pl.col("position") == position)
                for group, mask in (("changed", True), ("stable", False)):
                    rows = sub.filter(pl.col(flag) == mask)
                    results.append(
                        CarryoverResult(
                            metric=metric,
                            change=flag,
                            position=position,
                            group=group,
                            n=rows.height,
                            correlation=round(
                                _pearson(
                                    rows[prior_col].to_list(),
                                    rows[metric].to_list(),
                                ),
                                4,
                            ),
                        )
                    )
    return results


def vacated_opportunity_effect(
    seasons: list[int] | None = None,
    position: str = "WR",
) -> dict[str, float]:
    """Test whether arriving into vacated opportunity raises a mover's usage.

    Restricted to players who actually changed teams, since for a returning player
    "vacated share" mostly measures teammates who left around him rather than a
    role he was signed to fill.

    Args:
        seasons: Seasons to include.
        position: Position to test.

    Returns:
        Correlations of current usage against prior usage and against the vacated
        share waiting at the new team, plus the sample size behind them.
    """
    df = eligible_pairs(seasons)
    if df.is_empty():
        return {}

    movers = df.filter((pl.col("team_changed")) & (pl.col("position") == position))
    if movers.height < 3:
        log.warning("vacated_opportunity_effect: only %d movers for %s", movers.height, position)
        return {"n": float(movers.height)}

    return {
        "n": float(movers.height),
        "r_prior_usage": round(
            _pearson(movers["prior_target_share"].to_list(), movers["target_share"].to_list()), 4
        ),
        "r_vacated_share": round(
            _pearson(movers["vacated_target_share"].to_list(), movers["target_share"].to_list()), 4
        ),
    }


def summarize(results: list[CarryoverResult]) -> pl.DataFrame:
    """Pivot carryover results into a changed-vs-stable comparison table.

    Returns:
        One row per (metric, change, position) with both correlations and the
        gap between them — negative means the disruption cost carryover.
    """
    if not results:
        return pl.DataFrame()
    df = pl.DataFrame([r.__dict__ for r in results])
    wide = df.pivot(on="group", index=["metric", "change", "position"], values=["correlation", "n"])
    rename = {
        "correlation_changed": "r_changed",
        "correlation_stable": "r_stable",
        "n_changed": "n_changed",
        "n_stable": "n_stable",
    }
    wide = wide.rename({k: v for k, v in rename.items() if k in wide.columns})
    if "r_changed" in wide.columns and "r_stable" in wide.columns:
        wide = wide.with_columns((pl.col("r_changed") - pl.col("r_stable")).round(4).alias("gap"))
    return wide.sort(["metric", "change", "position"])
