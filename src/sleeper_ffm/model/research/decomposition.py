"""S1 — bonus-aware decomposition of league-scored fantasy points.

This league does not score like the market prices. On top of full PPR it pays
threshold bonuses: 2.5 for a 100-yard game, 5.0 for 200, 2.5 for a 40+ yard
touchdown, 1.0 for a 20-carry game, 2.5 for 300 passing yards. Every public
valuation — FantasyCalc, rotowire projections, ADP — prices generic scoring, so
any player whose profile converts the same raw production into more *bonus*
points than average is systematically underpriced here.

That is the hypothesis. The trap it has to survive is that bonus points are
mostly just a proxy for being good: a receiver with 1,400 yards clears 100 more
often than one with 700. Counting raw bonus points would rediscover "good
players are good" and dress it up as an edge.

So the quantity of interest is the *residual*: bonus points earned above what a
player's own baseline (non-bonus) production predicts. A player who scores 12
non-bonus points a game and banks 2.0 in bonuses is lumpy — boom weeks and bust
weeks — where one who banks 0.8 on the same baseline is steady. Lumpiness is
worth real points under this scoring, and it is invisible to a generic-scoring
market.

The finding only matters if that residual is a *trait* rather than noise, which
is what :func:`stickiness` tests: does a player's bonus residual in one season
predict the next? A null here is a real result and is reported as one.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import polars as pl

from sleeper_ffm.nflverse.loader import load_pbp, load_weekly
from sleeper_ffm.scoring.engine import load_scoring, score, stats_from_nflverse

log = logging.getLogger(__name__)

SKILL_POSITIONS = ("QB", "RB", "WR", "TE")

# Scoring keys that only fire at a threshold. Zeroing these gives the "generic
# scoring" counterfactual the market actually prices.
BONUS_KEYS = (
    "bonus_rec_yd_100",
    "bonus_rec_yd_200",
    "bonus_rush_yd_100",
    "bonus_rush_yd_200",
    "bonus_pass_yd_300",
    "bonus_pass_yd_400",
    "bonus_pass_cmp_25",
    "bonus_rush_att_20",
    "pass_td_40p",
    "rush_td_40p",
    "rec_td_40p",
)

# A player-season needs this many games before per-game rates are meaningful.
MIN_GAMES = 6

# Length threshold and payout for the long-touchdown bonuses, which the weekly
# box score cannot express — a 45-yard score and a 1-yard plunge are the same row.
TD40_YARDS = 40
TD40_POINTS = 2.5


@dataclass(frozen=True)
class StickinessResult:
    """Year-over-year persistence of one metric.

    Attributes:
        metric: Name of the measured quantity.
        position: Position group, or ``ALL``.
        n_pairs: Number of consecutive player-season pairs behind the estimate.
        correlation: Pearson r between season N and season N+1.
        r_squared: Squared correlation — the share of next-season variance explained.
    """

    metric: str
    position: str
    n_pairs: int
    correlation: float
    r_squared: float


def _scoring_variants() -> tuple[dict[str, float], dict[str, float]]:
    """Return (league scoring, the same scoring with every threshold bonus zeroed)."""
    league = load_scoring()
    generic = {k: v for k, v in league.items() if k not in BONUS_KEYS}
    return league, generic


def score_weekly_variants(seasons: list[int] | None = None) -> pl.DataFrame:
    """Score every player-week under league rules and under a bonus-free variant.

    Args:
        seasons: Seasons to score. Defaults to everything in the weekly cache.

    Returns:
        Weekly rows with ``fp_league``, ``fp_base`` (no bonuses) and ``fp_bonus``
        (the difference — points that exist only because of this league's rules).
    """
    weekly = load_weekly(seasons=seasons)
    if weekly.is_empty():
        log.warning("decomposition: no weekly data available")
        return pl.DataFrame()

    reg = weekly.filter(
        pl.col("season_type").eq("REG") & pl.col("position").is_in(list(SKILL_POSITIONS))
    )
    if reg.is_empty():
        return pl.DataFrame()

    league, generic = _scoring_variants()

    league_pts: list[float] = []
    base_pts: list[float] = []
    for row in reg.iter_rows(named=True):
        stats = stats_from_nflverse(row)
        league_pts.append(score(stats, league))
        base_pts.append(score(stats, generic))

    return reg.with_columns(
        pl.Series("fp_league", league_pts, dtype=pl.Float64),
        pl.Series("fp_base", base_pts, dtype=pl.Float64),
    ).with_columns(fp_bonus=pl.col("fp_league") - pl.col("fp_base"))


def long_td_bonuses(seasons: list[int]) -> pl.DataFrame:
    """Count each player's 40+ yard touchdowns from play-by-play.

    The weekly box score records that a touchdown happened, not how far it
    travelled, so the ``*_td_40p`` bonuses are invisible to the aggregate scoring
    path and silently score as zero. Recovering them needs play-by-play, where a
    scoring play carries its own yardage.

    Args:
        seasons: Seasons to scan. Seasons absent from the pbp cache are skipped.

    Returns:
        ``player_id`` / ``season`` / ``td40`` counts, pooling receiving, rushing
        and passing long scores — a quarterback earns the bonus on his own throw.
    """
    pbp = load_pbp(seasons=seasons)
    if pbp.is_empty():
        log.warning("long_td_bonuses: no play-by-play available")
        return pl.DataFrame(schema={"player_id": pl.Utf8, "season": pl.Int64, "td40": pl.UInt32})

    big = pbp.filter(
        pl.col("season_type").eq("REG")
        & pl.col("touchdown").eq(1)
        & pl.col("yards_gained").ge(TD40_YARDS)
    )
    if big.is_empty():
        return pl.DataFrame(schema={"player_id": pl.Utf8, "season": pl.Int64, "td40": pl.UInt32})

    scorers = [
        big.filter(pl.col("pass_touchdown").eq(1)).select(
            "season", pl.col("receiver_player_id").alias("player_id")
        ),
        big.filter(pl.col("rush_touchdown").eq(1)).select(
            "season", pl.col("rusher_player_id").alias("player_id")
        ),
        big.filter(pl.col("pass_touchdown").eq(1)).select(
            "season", pl.col("passer_player_id").alias("player_id")
        ),
    ]
    return (
        pl.concat(scorers)
        .filter(pl.col("player_id").is_not_null())
        .group_by(["season", "player_id"])
        .len("td40")
    )


def player_season_decomposition(
    seasons: list[int] | None = None,
    include_long_tds: bool = True,
) -> pl.DataFrame:
    """Aggregate weekly variant scores into per-player-season bonus profiles.

    The key column is ``bonus_residual``: bonus points per game above what this
    player's own baseline production predicts, fitted within position so that a
    quarterback's 300-yard bonuses are not compared against a tight end's.

    Args:
        seasons: Seasons to cover. Defaults to everything in the weekly cache.
        include_long_tds: Credit 40+ yard touchdown bonuses from play-by-play.
            Leaving this off reproduces what the aggregate scoring path sees,
            which understates bonus scoring by roughly a fifth to a third.

    Returns:
        One row per player-season with per-game baseline, bonus, and residual.
    """
    weekly = score_weekly_variants(seasons=seasons)
    if weekly.is_empty():
        return pl.DataFrame()

    agg = (
        weekly.group_by(["player_id", "season"])
        .agg(
            pl.len().alias("games"),
            pl.col("player_display_name").first().alias("name"),
            pl.col("position").first().alias("position"),
            pl.col("recent_team").last().alias("team"),
            pl.col("fp_league").sum().alias("fp_league"),
            pl.col("fp_base").sum().alias("fp_base"),
            pl.col("fp_bonus").sum().alias("fp_bonus"),
        )
        .filter(pl.col("games").ge(MIN_GAMES))
    )

    if include_long_tds:
        seasons_present = sorted(agg["season"].unique().to_list())
        td40 = long_td_bonuses(seasons_present)
        if td40.is_empty():
            log.warning("decomposition: long-TD bonuses requested but unavailable; scoring is low")
            agg = agg.with_columns(td40=pl.lit(0, dtype=pl.UInt32))
        else:
            agg = agg.join(td40, on=["season", "player_id"], how="left").with_columns(
                pl.col("td40").fill_null(0)
            )
        agg = agg.with_columns(
            fp_bonus=pl.col("fp_bonus") + pl.col("td40") * TD40_POINTS,
            fp_league=pl.col("fp_league") + pl.col("td40") * TD40_POINTS,
        )
    else:
        agg = agg.with_columns(td40=pl.lit(0, dtype=pl.UInt32))

    agg = agg.with_columns(
        fp_league_pg=pl.col("fp_league") / pl.col("games"),
        fp_base_pg=pl.col("fp_base") / pl.col("games"),
        fp_bonus_pg=pl.col("fp_bonus") / pl.col("games"),
    ).with_columns(
        bonus_share=pl.when(pl.col("fp_league") != 0)
        .then(pl.col("fp_bonus") / pl.col("fp_league"))
        .otherwise(None)
    )

    return _add_bonus_residual(agg)


def _add_bonus_residual(df: pl.DataFrame) -> pl.DataFrame:
    """Fit bonus-per-game on baseline-per-game within position; keep the residual.

    A straight line per position is deliberately crude. The point is not to model
    the bonus curve precisely but to strip out the part of bonus scoring that is
    just "this player produces a lot", leaving the part that is profile.
    """
    frames: list[pl.DataFrame] = []
    for (position,), group in df.group_by(["position"]):
        slope, intercept = _ols(
            group["fp_base_pg"].to_list(),
            group["fp_bonus_pg"].to_list(),
        )
        frames.append(
            group.with_columns(
                bonus_expected_pg=(pl.col("fp_base_pg") * slope + intercept),
            ).with_columns(bonus_residual=pl.col("fp_bonus_pg") - pl.col("bonus_expected_pg"))
        )
        log.debug("bonus fit %s: slope=%.4f intercept=%.4f", position, slope, intercept)
    return pl.concat(frames).sort(["season", "player_id"])


def _ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Least-squares slope and intercept, returning a flat fit when x has no spread."""
    pairs = [(x, y) for x, y in zip(xs, ys, strict=True) if x is not None and y is not None]
    n = len(pairs)
    if n < 2:
        return 0.0, 0.0
    mean_x = sum(p[0] for p in pairs) / n
    mean_y = sum(p[1] for p in pairs) / n
    var_x = sum((p[0] - mean_x) ** 2 for p in pairs)
    if var_x == 0:
        return 0.0, mean_y
    cov = sum((p[0] - mean_x) * (p[1] - mean_y) for p in pairs)
    slope = cov / var_x
    return slope, mean_y - slope * mean_x


def _pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation, returning 0.0 when either series is constant."""
    pairs = [(x, y) for x, y in zip(xs, ys, strict=True) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return 0.0
    mean_x = sum(p[0] for p in pairs) / n
    mean_y = sum(p[1] for p in pairs) / n
    sx = math.sqrt(sum((p[0] - mean_x) ** 2 for p in pairs))
    sy = math.sqrt(sum((p[1] - mean_y) ** 2 for p in pairs))
    if sx == 0 or sy == 0:
        return 0.0
    cov = sum((p[0] - mean_x) * (p[1] - mean_y) for p in pairs)
    return cov / (sx * sy)


def stickiness(
    df: pl.DataFrame,
    metrics: tuple[str, ...] = ("fp_base_pg", "fp_bonus_pg", "bonus_share", "bonus_residual"),
    by_position: bool = True,
) -> list[StickinessResult]:
    """Measure year-over-year persistence of each metric.

    Pairs each player-season with that same player's next season and correlates
    the two. A metric that does not persist cannot be forecast, whatever its
    in-season effect size.

    Args:
        df: Output of :func:`player_season_decomposition`.
        metrics: Column names to test.
        by_position: Also report per-position results alongside the pooled one.

    Returns:
        One result per metric (and per position when requested), pooled first.
    """
    if df.is_empty():
        return []

    nxt = df.select(
        "player_id",
        (pl.col("season") - 1).alias("season"),
        *[pl.col(m).alias(f"next_{m}") for m in metrics],
    )
    paired = df.join(nxt, on=["player_id", "season"], how="inner")

    results: list[StickinessResult] = []
    for metric in metrics:
        results.append(_stickiness_one(paired, metric, "ALL"))
        if by_position:
            for (position,), group in paired.group_by(["position"]):
                results.append(_stickiness_one(group, metric, str(position)))
    return results


def _stickiness_one(paired: pl.DataFrame, metric: str, position: str) -> StickinessResult:
    sub = paired.filter(pl.col(metric).is_not_null() & pl.col(f"next_{metric}").is_not_null())
    r = _pearson(sub[metric].to_list(), sub[f"next_{metric}"].to_list())
    return StickinessResult(
        metric=metric,
        position=position,
        n_pairs=sub.height,
        correlation=round(r, 4),
        r_squared=round(r * r, 4),
    )
