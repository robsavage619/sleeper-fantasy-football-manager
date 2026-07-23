"""S6 — what draft capital is worth, priced under this league's rules.

Public rookie hit rates are computed for generic leagues: 12 teams, standard
scoring, "top-24 finish" as the bar. None of those describe this one. Ten teams
means a shallower pool and a higher replacement level, and the bonus structure
pays a different game. A hit rate that is true at 12 teams overstates what a
player is worth here, because clearing the bar is easier when fewer people are
starting.

So this recomputes the whole thing from scratch against the league's own
replacement thresholds, which `valuation.replacement_thresholds` derives from the
roster settings rather than convention.

**Survivorship is the trap this module exists to avoid.** A drafted player who
never records a snap has no weekly rows at all. Joining outcomes onto stats would
silently drop him, and every hit rate would be computed over the players who made
it — which is the population you cannot observe on draft day. The cohort here is
anchored on the draft class itself, and a player with no recorded production is a
miss, not a missing value.

Rates are reported with Wilson score intervals rather than bare proportions. At
roughly twenty players per position-round cell, the difference between 20% and 35%
is often not a difference at all, and a point estimate invites reading noise as
signal.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import polars as pl

from sleeper_ffm.model.valuation import (
    SKILL_POSITIONS,
    compute_season_totals,
    replacement_thresholds,
)
from sleeper_ffm.nflverse.loader import load_id_map

log = logging.getLogger(__name__)

# Years of a player's career counted when asking whether he ever became startable.
# Three covers the rookie contract window a dynasty manager is buying.
DEFAULT_HORIZON = 3

# Undrafted players are pooled into this pseudo-round so the cohort stays complete.
UNDRAFTED_ROUND = 8


@dataclass(frozen=True)
class HitRate:
    """Probability that a draft cohort produced a startable fantasy season.

    Attributes:
        position: Position group, or ``ALL``.
        bucket: Draft-capital bucket (round number, or ``UNDRAFTED_ROUND``).
        n: Players in the cohort, including those who never played.
        hits: Players who cleared the league's replacement line at least once.
        rate: ``hits / n``.
        ci_low: Lower bound of the 95% Wilson score interval.
        ci_high: Upper bound of the 95% Wilson score interval.
    """

    position: str
    bucket: int
    n: int
    hits: int
    rate: float
    ci_low: float
    ci_high: float


def wilson_interval(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Return the Wilson score interval for a binomial proportion.

    Preferred over the normal approximation because these cells are small and
    the rates sit near 0 or 1, where the normal interval runs outside [0, 1] and
    badly understates uncertainty.

    Args:
        hits: Successes observed.
        n: Trials.
        z: Standard normal quantile; 1.96 gives a 95% interval.

    Returns:
        ``(low, high)``, or ``(0.0, 0.0)`` when ``n`` is zero.
    """
    if n == 0:
        return 0.0, 0.0
    p = hits / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


def draft_cohort(draft_years: list[int]) -> pl.DataFrame:
    """Every drafted and undrafted skill-position player entering in these years.

    This is the denominator. It is built from the ID map rather than from stats
    precisely so that players who never produced remain in it.

    Args:
        draft_years: Entry years to include.

    Returns:
        ``gsis_id`` / ``name`` / ``position`` / ``draft_year`` / ``draft_round`` /
        ``draft_ovr`` rows, with undrafted players assigned ``UNDRAFTED_ROUND``.
    """
    id_map = load_id_map()
    cohort = (
        id_map.filter(
            pl.col("gsis_id").is_not_null()
            & pl.col("draft_year").is_in(draft_years)
            & pl.col("position").is_in(list(SKILL_POSITIONS))
        )
        .select(
            "gsis_id",
            "name",
            "position",
            pl.col("draft_year").cast(pl.Int64),
            "draft_round",
            "draft_ovr",
        )
        .unique(subset=["gsis_id"])
    )
    return cohort.with_columns(
        bucket=pl.col("draft_round").fill_null(UNDRAFTED_ROUND).cast(pl.Int64)
    )


def cohort_outcomes(
    draft_years: list[int],
    horizon: int = DEFAULT_HORIZON,
) -> pl.DataFrame:
    """Attach each cohort member's best league-scored season within the horizon.

    Args:
        draft_years: Entry years to include.
        horizon: Seasons from entry to consider (1 = rookie year only).

    Returns:
        The cohort with ``best_fp``, ``best_season`` and a boolean ``hit`` marking
        whether the player ever cleared his position's replacement line. Players
        with no recorded production carry ``best_fp`` of 0.0 and ``hit`` False.
    """
    cohort = draft_cohort(draft_years)
    if cohort.is_empty():
        log.warning("cohort_outcomes: no cohort for draft years %s", draft_years)
        return cohort

    seasons = sorted({y + offset for y in draft_years for offset in range(horizon)})

    # The replacement line must be computed within each season. Ranking the Nth
    # best player-season across a decade is a far harsher bar than being the Nth
    # best player in a given year — pooling here understates hit rates severalfold.
    per_season: list[pl.DataFrame] = []
    for season in seasons:
        totals = compute_season_totals(seasons=[season])
        if totals.is_empty():
            continue
        thresholds = replacement_thresholds(totals)
        log.debug("replacement line %d: %s", season, thresholds)
        per_season.append(
            totals.select(
                "gsis_id",
                "season",
                "season_fp",
                pl.col("position")
                .replace_strict(thresholds, default=None)
                .alias("replacement_line"),
            )
        )

    if not per_season:
        log.warning("cohort_outcomes: no season totals available")
        return cohort.with_columns(best_fp=pl.lit(0.0), hit=pl.lit(False))

    scored = pl.concat(per_season)

    # Restrict each player's seasons to his own horizon, then ask whether any of
    # them cleared that season's line.
    windowed = scored.join(
        cohort.select("gsis_id", "draft_year"), on="gsis_id", how="inner"
    ).filter(pl.col("season").is_between(pl.col("draft_year"), pl.col("draft_year") + horizon - 1))

    best = (
        windowed.with_columns(cleared=pl.col("season_fp") >= pl.col("replacement_line"))
        .group_by("gsis_id")
        .agg(
            pl.col("season_fp").max().alias("best_fp"),
            pl.col("cleared").any().alias("hit"),
        )
    )

    # A left join keeps players who never appear in the stats — the whole point.
    return cohort.join(best, on="gsis_id", how="left").with_columns(
        pl.col("best_fp").fill_null(0.0),
        pl.col("hit").fill_null(False),
    )


def hit_rates(outcomes: pl.DataFrame, by_position: bool = True) -> list[HitRate]:
    """Summarise startable-season rates by draft-capital bucket.

    Args:
        outcomes: Output of :func:`cohort_outcomes`.
        by_position: Report per-position cells in addition to the pooled ones.

    Returns:
        One entry per (position, bucket), pooled ``ALL`` rows first.
    """
    if outcomes.is_empty() or "hit" not in outcomes.columns:
        return []

    results: list[HitRate] = []
    groups = ["ALL", *sorted(SKILL_POSITIONS)] if by_position else ["ALL"]
    for position in groups:
        sub = outcomes if position == "ALL" else outcomes.filter(pl.col("position") == position)
        for bucket in sorted(sub["bucket"].unique().to_list()):
            cell = sub.filter(pl.col("bucket") == bucket)
            n = cell.height
            hits = int(cell["hit"].sum())
            low, high = wilson_interval(hits, n)
            results.append(
                HitRate(
                    position=position,
                    bucket=int(bucket),
                    n=n,
                    hits=hits,
                    rate=round(hits / n, 4) if n else 0.0,
                    ci_low=round(low, 4),
                    ci_high=round(high, 4),
                )
            )
    return results


def summarize(rates: list[HitRate]) -> pl.DataFrame:
    """Render hit rates as a table sorted by position then draft bucket."""
    if not rates:
        return pl.DataFrame()
    return pl.DataFrame([r.__dict__ for r in rates]).sort(["position", "bucket"])
