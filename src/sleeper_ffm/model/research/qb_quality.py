"""S3 — how much does quarterback quality move pass-catcher scoring?

S2 measured what a quarterback change does to a receiver's *role* and found it the
mildest of three disruptions. The Q5 literature review argued that is the wrong
target: published tier studies find target volume barely moves across quarterback
tiers while points per target fall sharply. A bad quarterback does not take the
role away, it makes the role worth less.

Role stability and scoring level are close to orthogonal — a receiver whose
production is uniformly depressed can still have perfectly stable year-over-year
carryover. So this study measures the level directly.

Identification is within-player. Comparing receivers who happen to play with good
quarterbacks against those who do not would mostly rediscover that good offenses
employ good players. Instead this pairs each receiver's consecutive seasons and
asks whether the *change* in his quarterback's accuracy predicts the *change* in
his points per target. The receiver is his own control, so his hands, route
running and role largely difference out.

Quarterback quality is completion percentage over expectation from Next Gen Stats,
which is already adjusted for throw difficulty — a quarterback on a bad team is
not penalised for having to throw deep and late.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import polars as pl

from sleeper_ffm.model.context_table import load_context_table
from sleeper_ffm.model.valuation import score_weekly
from sleeper_ffm.nflverse.loader import load_ngs

log = logging.getLogger(__name__)

PASS_CATCHERS = ("WR", "TE")

# NGS publishes a season aggregate on the sentinel week 0 alongside real weeks.
_SEASON_AGGREGATE_WEEK = 0

# Below this a quarterback's CPOE is mostly noise and his receivers' rates are thin.
MIN_QB_ATTEMPTS = 150
MIN_TARGETS = 40


@dataclass(frozen=True)
class QbEffect:
    """Estimated effect of quarterback accuracy on pass-catcher scoring.

    Attributes:
        position: Position group measured.
        n: Player-season pairs behind the estimate.
        correlation: Pearson r between change in QB CPOE and change in points per target.
        slope: Fantasy points per target gained per point of CPOE.
        per_game_effect: Points per game implied for a one-standard-deviation
            CPOE swing at that position's median target volume.
    """

    position: str
    n: int
    correlation: float
    slope: float
    per_game_effect: float


def qb_season_quality(seasons: list[int]) -> pl.DataFrame:
    """Return each quarterback's season CPOE and attempt volume.

    Args:
        seasons: Seasons to load.

    Returns:
        ``player_id`` / ``season`` / ``cpoe`` / ``attempts`` rows, restricted to
        quarterbacks with enough attempts for the rate to mean anything.
    """
    ngs = load_ngs("passing", seasons=seasons)
    if ngs.is_empty():
        log.warning("qb_season_quality: no NGS passing data")
        return pl.DataFrame(schema={"player_id": pl.Utf8, "season": pl.Int64, "cpoe": pl.Float64})

    return (
        ngs.filter(pl.col("week").eq(_SEASON_AGGREGATE_WEEK))
        .select(
            pl.col("player_gsis_id").alias("player_id"),
            pl.col("season").cast(pl.Int64),
            pl.col("completion_percentage_above_expectation").alias("cpoe"),
            pl.col("attempts"),
        )
        .filter(pl.col("cpoe").is_not_null() & pl.col("attempts").ge(MIN_QB_ATTEMPTS))
        .unique(subset=["player_id", "season"])
    )


def receiver_efficiency(seasons: list[int]) -> pl.DataFrame:
    """Per-player-season points per target and per game, under league scoring."""
    scored = score_weekly(seasons=seasons)
    if scored.is_empty():
        return pl.DataFrame()

    return (
        scored.filter(pl.col("position").is_in(list(PASS_CATCHERS)))
        .group_by(["player_id", "season"])
        .agg(
            pl.len().alias("games"),
            pl.col("position").first().alias("position"),
            pl.col("player_display_name").first().alias("name"),
            pl.col("fp_sffm").sum().alias("fp"),
            pl.col("targets").fill_null(0).sum().alias("targets"),
        )
        .filter(pl.col("targets").ge(MIN_TARGETS))
        .with_columns(
            fp_per_target=pl.col("fp") / pl.col("targets"),
            fp_per_game=pl.col("fp") / pl.col("games"),
            targets_per_game=pl.col("targets") / pl.col("games"),
        )
    )


def build_panel(seasons: list[int]) -> pl.DataFrame:
    """Pair consecutive seasons per receiver with the CPOE of his team's primary QB.

    Args:
        seasons: Seasons to cover.

    Returns:
        One row per receiver season-pair with ``d_cpoe`` and ``d_fp_per_target``.
    """
    context = load_context_table()
    if context.is_empty():
        log.warning("build_panel: context table empty")
        return pl.DataFrame()

    quality = qb_season_quality(seasons)
    efficiency = receiver_efficiency(seasons)
    if quality.is_empty() or efficiency.is_empty():
        return pl.DataFrame()

    # The quarterback each receiver actually played with, via his team-season.
    team_qb = context.select("player_id", "season", pl.col("primary_qb_id").alias("qb_id")).filter(
        pl.col("qb_id").is_not_null()
    )

    panel = (
        efficiency.join(team_qb, on=["player_id", "season"], how="inner")
        .join(
            quality.rename({"player_id": "qb_id", "cpoe": "qb_cpoe"}).drop("attempts"),
            on=["qb_id", "season"],
            how="inner",
        )
        .select(
            "player_id",
            "season",
            "position",
            "name",
            "qb_id",
            "qb_cpoe",
            "fp_per_target",
            "fp_per_game",
            "targets_per_game",
        )
    )

    prior = panel.select(
        "player_id",
        (pl.col("season") + 1).alias("season"),
        pl.col("qb_cpoe").alias("prior_qb_cpoe"),
        pl.col("fp_per_target").alias("prior_fp_per_target"),
        pl.col("targets_per_game").alias("prior_targets_per_game"),
    )

    return panel.join(prior, on=["player_id", "season"], how="inner").with_columns(
        d_cpoe=pl.col("qb_cpoe") - pl.col("prior_qb_cpoe"),
        d_fp_per_target=pl.col("fp_per_target") - pl.col("prior_fp_per_target"),
        d_targets_per_game=pl.col("targets_per_game") - pl.col("prior_targets_per_game"),
    )


def _as_float(value: object) -> float:
    """Narrow a polars aggregate (typed as any column dtype) to a float."""
    return float(value) if isinstance(value, (int, float)) else 0.0


def _ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    pairs = [(x, y) for x, y in zip(xs, ys, strict=True) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return 0.0, 0.0
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    var = sum((p[0] - mx) ** 2 for p in pairs)
    if var == 0:
        return 0.0, my
    cov = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    slope = cov / var
    return slope, my - slope * mx


def _pearson(xs: list[float], ys: list[float]) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys, strict=True) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return float("nan")
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sx = math.sqrt(sum((p[0] - mx) ** 2 for p in pairs))
    sy = math.sqrt(sum((p[1] - my) ** 2 for p in pairs))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((p[0] - mx) * (p[1] - my) for p in pairs) / (sx * sy)


def estimate_effect(panel: pl.DataFrame, outcome: str = "d_fp_per_target") -> list[QbEffect]:
    """Regress the change in a receiver outcome on the change in his QB's CPOE.

    Args:
        panel: Output of :func:`build_panel`.
        outcome: Differenced outcome column to explain.

    Returns:
        One effect estimate per position, plus a pooled ``ALL`` row.
    """
    if panel.is_empty():
        return []

    results: list[QbEffect] = []
    for position in ("ALL", *PASS_CATCHERS):
        sub = panel if position == "ALL" else panel.filter(pl.col("position") == position)
        sub = sub.filter(pl.col("d_cpoe").is_not_null() & pl.col(outcome).is_not_null())
        if sub.height < 3:
            continue
        xs = sub["d_cpoe"].to_list()
        ys = sub[outcome].to_list()
        slope, _ = _ols(xs, ys)
        cpoe_sd = _as_float(sub["d_cpoe"].std())
        median_targets = _as_float(sub["targets_per_game"].median())
        results.append(
            QbEffect(
                position=position,
                n=sub.height,
                correlation=round(_pearson(xs, ys), 4),
                slope=round(slope, 4),
                per_game_effect=round(slope * cpoe_sd * median_targets, 3),
            )
        )
    return results
