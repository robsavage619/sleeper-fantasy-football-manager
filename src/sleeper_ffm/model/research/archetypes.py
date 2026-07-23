"""S4 — do players age by archetype rather than by position?

The engine's age curves are league-wide per position: every running back is
assumed to decline on the same schedule. That is the documented "next real
improvement", and the Q6 literature review found no published archetype-conditional
aging curves anywhere reachable — so this builds rather than reproduces.

The hypothesis is that a position label is too coarse to describe how a player
ages. A back who catches passes and a back who runs between the tackles are
different jobs with different physical demands, and the same is true of a receiver
who wins deep against one who works underneath. If archetype conditions aging, the
engine's single curve per position is averaging two different populations.

Archetypes are defined by observable usage ratios rather than by clustering.
K-means over usage features would produce groups that are hard to name, hard to
validate, and liable to shift with the sample; a ratio split is legible, stable,
and testable. The cost is that the cut points are chosen rather than learned, and
the study is only as good as they are — which is why the split is at the within-
position median rather than at a hand-picked threshold.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import polars as pl

from sleeper_ffm.model.context_table import load_context_table
from sleeper_ffm.model.valuation import score_weekly

log = logging.getLogger(__name__)

# A player-season needs this many games before its usage mix and scoring rate mean
# anything; part-seasons distort both the archetype assignment and the age curve.
MIN_GAMES = 8

# Ages outside this band have too few observations to estimate a curve.
MIN_AGE = 22
MAX_AGE = 33


@dataclass(frozen=True)
class AgingPoint:
    """Mean scoring rate for one archetype at one age.

    Attributes:
        position: Position group.
        archetype: Archetype label within that position.
        age: Season age, rounded to whole years.
        n: Player-seasons observed.
        mean_fp_per_game: Mean league-scored points per game.
        se: Standard error of that mean.
    """

    position: str
    archetype: str
    age: int
    n: int
    mean_fp_per_game: float
    se: float


def _usage_frame(seasons: list[int]) -> pl.DataFrame:
    """Per-player-season usage mix and scoring rate, joined to season age."""
    scored = score_weekly(seasons=seasons)
    if scored.is_empty():
        return pl.DataFrame()

    agg = (
        scored.filter(pl.col("position").is_in(["RB", "WR", "TE"]))
        .group_by(["player_id", "season"])
        .agg(
            pl.len().alias("games"),
            pl.col("position").first().alias("position"),
            pl.col("player_display_name").first().alias("name"),
            pl.col("fp_sffm").sum().alias("fp"),
            pl.col("targets").fill_null(0).sum().alias("targets"),
            pl.col("carries").fill_null(0).sum().alias("carries"),
            pl.col("receiving_yards").fill_null(0).sum().alias("rec_yards"),
            pl.col("receptions").fill_null(0).sum().alias("receptions"),
        )
        .filter(pl.col("games").ge(MIN_GAMES))
        .with_columns(fp_per_game=pl.col("fp") / pl.col("games"))
    )

    context = load_context_table()
    if context.is_empty() or "season_age" not in context.columns:
        log.warning("_usage_frame: no season_age available; archetype aging cannot be computed")
        return pl.DataFrame()

    return agg.join(
        context.select("player_id", "season", "season_age"),
        on=["player_id", "season"],
        how="inner",
    ).filter(pl.col("season_age").is_not_null())


def assign_archetypes(usage: pl.DataFrame) -> pl.DataFrame:
    """Label each player-season with an archetype inside its position.

    Running backs split on receiving share of total touches: a back who catches
    passes is doing a different job from one who only runs. Receivers and tight
    ends split on yards per reception, which separates field-stretchers from
    underneath and possession roles.

    Cut points are each position's own median, so the groups are balanced by
    construction and the split does not smuggle in a threshold chosen to produce a
    result.

    Args:
        usage: Output of :func:`_usage_frame`.

    Returns:
        The frame with an ``archetype`` column.
    """
    if usage.is_empty():
        return usage

    frames: list[pl.DataFrame] = []
    for (position,), group in usage.group_by(["position"]):
        if position == "RB":
            metric = (pl.col("targets") / (pl.col("targets") + pl.col("carries"))).alias("_metric")
            low, high = "grinder", "receiving_back"
        else:
            metric = (pl.col("rec_yards") / pl.col("receptions").clip(lower_bound=1)).alias(
                "_metric"
            )
            low, high = "possession", "field_stretcher"

        with_metric = group.with_columns(metric)
        median = with_metric["_metric"].median()
        if median is None:
            continue
        frames.append(
            with_metric.with_columns(
                archetype=pl.when(pl.col("_metric") >= median)
                .then(pl.lit(high))
                .otherwise(pl.lit(low))
            ).drop("_metric")
        )

    return pl.concat(frames) if frames else pl.DataFrame()


def aging_curve(usage: pl.DataFrame) -> list[AgingPoint]:
    """Mean scoring rate by position, archetype and whole-year age.

    Args:
        usage: Output of :func:`assign_archetypes`.

    Returns:
        One point per (position, archetype, age) cell inside the age band.
    """
    if usage.is_empty() or "archetype" not in usage.columns:
        return []

    binned = usage.with_columns(age=pl.col("season_age").round(0).cast(pl.Int64)).filter(
        pl.col("age").is_between(MIN_AGE, MAX_AGE)
    )

    grouped = (
        binned.group_by(["position", "archetype", "age"])
        .agg(
            pl.len().alias("n"),
            pl.col("fp_per_game").mean().alias("mean_fp"),
            pl.col("fp_per_game").std().alias("sd_fp"),
        )
        .sort(["position", "archetype", "age"])
    )

    points: list[AgingPoint] = []
    for row in grouped.iter_rows(named=True):
        n = int(row["n"])
        sd = float(row["sd_fp"] or 0.0)
        points.append(
            AgingPoint(
                position=str(row["position"]),
                archetype=str(row["archetype"]),
                age=int(row["age"]),
                n=n,
                mean_fp_per_game=round(float(row["mean_fp"]), 3),
                se=round(sd / math.sqrt(n), 3) if n else 0.0,
            )
        )
    return points


def decline_rates(usage: pl.DataFrame, pivot_age: int = 27) -> pl.DataFrame:
    """Compare scoring before and after a pivot age, by archetype.

    A single before/after contrast is a blunt summary of a curve, but it is what
    the sample supports: per-age cells run to a few dozen player-seasons, and a
    fitted curve would imply a precision the data does not carry.

    Args:
        usage: Output of :func:`assign_archetypes`.
        pivot_age: Age at which the "older" group begins.

    Returns:
        One row per (position, archetype) with mean scoring either side of the
        pivot and the proportional decline between them.
    """
    if usage.is_empty() or "archetype" not in usage.columns:
        return pl.DataFrame()

    banded = usage.with_columns(age=pl.col("season_age").round(0).cast(pl.Int64)).filter(
        pl.col("age").is_between(MIN_AGE, MAX_AGE)
    )

    return (
        banded.with_columns(older=pl.col("age") >= pivot_age)
        .group_by(["position", "archetype", "older"])
        .agg(pl.len().alias("n"), pl.col("fp_per_game").mean().alias("mean_fp"))
        .pivot(on="older", index=["position", "archetype"], values=["n", "mean_fp"])
        .rename(
            lambda c: (
                c.replace("mean_fp_true", "mean_fp_older")
                .replace("mean_fp_false", "mean_fp_younger")
                .replace("n_true", "n_older")
                .replace("n_false", "n_younger")
            )
        )
        .with_columns(
            decline_pct=(
                (pl.col("mean_fp_younger") - pl.col("mean_fp_older"))
                / pl.col("mean_fp_younger")
                * 100
            ).round(2)
        )
        .sort(["position", "archetype"])
    )


def within_player_change(usage: pl.DataFrame) -> pl.DataFrame:
    """Year-over-year change in scoring for the same player, by age and archetype.

    Cross-sectional aging comparisons are invalid here. A 31-year-old still
    starting is a survivor, selected on having aged well, while his declining
    peers have left the league — so comparing age groups makes older cohorts look
    *better*. Differencing within a player removes that: each player is his own
    baseline, and the quantity is how much he changed, not how good he was.

    Attrition still biases this toward zero, because a player who falls out of the
    league entirely contributes no change at all. :func:`attrition_rate` measures
    that missing half directly.

    Args:
        usage: Output of :func:`assign_archetypes`.

    Returns:
        Consecutive-season pairs with ``d_fp_per_game`` and the age at the start.
    """
    if usage.is_empty() or "archetype" not in usage.columns:
        return pl.DataFrame()

    nxt = usage.select(
        "player_id",
        (pl.col("season") - 1).alias("season"),
        pl.col("fp_per_game").alias("next_fp_per_game"),
    )
    return (
        usage.join(nxt, on=["player_id", "season"], how="inner")
        .with_columns(
            age=pl.col("season_age").round(0).cast(pl.Int64),
            d_fp_per_game=pl.col("next_fp_per_game") - pl.col("fp_per_game"),
        )
        .filter(pl.col("age").is_between(MIN_AGE, MAX_AGE))
    )


def attrition_rate(usage: pl.DataFrame) -> pl.DataFrame:
    """Probability a qualifying player-season is not followed by another one.

    This is the mortality-table view: rather than asking how much survivors
    decline, it asks how likely a player is to stop being a startable option at
    all. It captures precisely the players a within-player analysis has to drop.

    The final season in the data is excluded, since no player can have a
    successor season there and every one of them would count as a death.

    Args:
        usage: Output of :func:`assign_archetypes`.

    Returns:
        One row per (position, archetype, age band) with the attrition rate.
    """
    if usage.is_empty() or "archetype" not in usage.columns:
        return pl.DataFrame()

    last_season = usage["season"].max()
    survived = usage.select(
        "player_id", (pl.col("season") - 1).alias("season"), pl.lit(True).alias("survived")
    )

    return (
        usage.filter(pl.col("season") < last_season)
        .join(survived, on=["player_id", "season"], how="left")
        .with_columns(
            age=pl.col("season_age").round(0).cast(pl.Int64),
            died=pl.col("survived").is_null(),
        )
        .filter(pl.col("age").is_between(MIN_AGE, MAX_AGE))
        .with_columns(
            age_band=pl.when(pl.col("age") < 25)
            .then(pl.lit("22-24"))
            .when(pl.col("age") < 28)
            .then(pl.lit("25-27"))
            .otherwise(pl.lit("28+"))
        )
        .group_by(["position", "archetype", "age_band"])
        .agg(pl.len().alias("n"), pl.col("died").mean().alias("attrition_rate"))
        .sort(["position", "archetype", "age_band"])
    )


def build(seasons: list[int]) -> pl.DataFrame:
    """Load, label and return archetype-tagged player-seasons."""
    return assign_archetypes(_usage_frame(seasons))
