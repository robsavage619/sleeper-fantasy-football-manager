"""Regression flags — buy-low and sell-high candidates from unsustainable scoring.

Fantasy points are noisy; touchdowns are the noisiest part. A player scoring far more
TDs than his yardage volume implies is riding variance that tends to correct — a
sell-high. One scoring far fewer is getting unlucky on the same real usage — a buy-low
the market hasn't caught up to.

The engine computes each player's touchdowns-over-expected (``td_oe``): actual total TDs
minus what his total yardage would produce at his position's league-average TD-per-yard
rate. It complements the descriptive TD-dependence figure already in
:mod:`sleeper_ffm.model.sabermetrics` by turning it into a directional, actionable call.

This is a lean, not a projection: usage can be real and sticky, and elite players do
sustain high TD rates. The flag says "the points ran ahead of / behind the process,"
which is a reason to look, not a verdict.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import polars as pl

from sleeper_ffm.config import DEFAULT_VALUE_SEASON
from sleeper_ffm.model.valuation import SKILL_POSITIONS
from sleeper_ffm.nflverse.loader import load_id_map, load_weekly

log = logging.getLogger(__name__)

# Minimum yardage volume before td_oe is meaningful (filters low-sample noise).
_MIN_YARDS: int = 250
# |td_oe| beyond this trips a directional flag.
_FLAG_TDS: float = 2.0

_YARD_COLS = ("rushing_yards", "receiving_yards")
_TD_COLS = ("rushing_tds", "receiving_tds")


@dataclass
class RegressionFlag:
    """One player's TD-over-expected signal."""

    player_id: str
    name: str
    position: str
    team: str
    total_yards: float
    total_tds: float
    expected_tds: float  # total_yards * position TD-per-yard baseline
    td_oe: float  # actual - expected; +ve = lucky (sell), -ve = unlucky (buy)
    verdict: str  # "SELL-HIGH" | "BUY-LOW" | "NEUTRAL"
    note: str = ""


@dataclass
class RegressionBoard:
    """Ranked regression candidates."""

    season: int
    baselines: dict[str, float]  # position -> TD per yard
    sell_high: list[RegressionFlag]  # most over-expected first
    buy_low: list[RegressionFlag]  # most under-expected first
    warnings: list[str] = field(default_factory=list)


def compute_td_regression(
    rows: list[dict],
    min_yards: int = _MIN_YARDS,
) -> tuple[dict[str, float], list[RegressionFlag]]:
    """Compute position TD-per-yard baselines and per-player td_oe. Pure.

    Args:
        rows: ``[{sid, name, position, team, total_yards, total_tds}, ...]``.
        min_yards: Minimum yardage before a player is flagged.

    Returns:
        ``(baselines, flags)`` — ``{position: td_per_yard}`` and one flag per row.
    """
    baselines: dict[str, float] = {}
    for pos in SKILL_POSITIONS:
        pos_rows = [r for r in rows if r["position"] == pos]
        yards = sum(r["total_yards"] for r in pos_rows)
        tds = sum(r["total_tds"] for r in pos_rows)
        if yards > 0:
            baselines[pos] = tds / yards

    flags: list[RegressionFlag] = []
    for r in rows:
        pos = r["position"]
        rate = baselines.get(pos)
        if rate is None or r["total_yards"] < min_yards:
            continue
        expected = r["total_yards"] * rate
        td_oe = r["total_tds"] - expected
        if td_oe >= _FLAG_TDS:
            verdict = "SELL-HIGH"
            note = f"+{td_oe:.1f} TDs over expected — TD rate likely regresses down"
        elif td_oe <= -_FLAG_TDS:
            verdict = "BUY-LOW"
            note = f"{td_oe:.1f} TDs below expected — same usage, unlucky finish"
        else:
            verdict = "NEUTRAL"
            note = "TD rate roughly matches yardage volume"
        flags.append(
            RegressionFlag(
                player_id=r["sid"],
                name=r["name"],
                position=pos,
                team=r["team"],
                total_yards=round(r["total_yards"], 1),
                total_tds=round(r["total_tds"], 1),
                expected_tds=round(expected, 1),
                td_oe=round(td_oe, 1),
                verdict=verdict,
                note=note,
            )
        )
    return baselines, flags


def _aggregate_rows(season: int) -> list[dict]:
    """Aggregate one season's weekly stats to per-player yardage/TD totals."""
    weekly = load_weekly(seasons=[season])
    if weekly.is_empty() or "season_type" not in weekly.columns:
        return []
    reg = weekly.filter(
        (pl.col("season_type") == "REG") & (pl.col("position").is_in(list(SKILL_POSITIONS)))
    )
    if reg.is_empty():
        return []

    yard_cols = [c for c in _YARD_COLS if c in reg.columns]
    td_cols = [c for c in _TD_COLS if c in reg.columns]
    if not yard_cols or not td_cols:
        return []

    agg = reg.group_by("player_id").agg(
        [
            *(pl.col(c).sum().alias(c) for c in yard_cols),
            *(pl.col(c).sum().alias(c) for c in td_cols),
            pl.col("position").last().alias("position"),
            pl.col("player_display_name").last().alias("name"),
            pl.col("recent_team").last().alias("team"),
        ]
    )

    id_map = load_id_map()
    id_slim = (
        id_map.select(["gsis_id", "sleeper_id"])
        .filter(pl.col("gsis_id").is_not_null() & pl.col("sleeper_id").is_not_null())
        .with_columns(
            pl.col("sleeper_id").cast(pl.Int64, strict=False).cast(pl.Utf8).alias("sleeper_id_str")
        )
        .filter(pl.col("sleeper_id_str").is_not_null())
        .select(["gsis_id", "sleeper_id_str"])
    )
    agg = agg.join(id_slim, left_on="player_id", right_on="gsis_id", how="left")

    rows: list[dict] = []
    for r in agg.iter_rows(named=True):
        total_yards = sum(float(r.get(c) or 0.0) for c in yard_cols)
        total_tds = sum(float(r.get(c) or 0.0) for c in td_cols)
        rows.append(
            {
                "sid": r.get("sleeper_id_str") or "",
                "name": r.get("name") or "?",
                "position": r["position"],
                "team": r.get("team") or "FA",
                "total_yards": total_yards,
                "total_tds": total_tds,
            }
        )
    return rows


def build_regression(season: int | None = None, top: int = 15) -> RegressionBoard:
    """Build the regression board for a season.

    Returns:
        A :class:`RegressionBoard` with sell-high and buy-low shortlists.
    """
    season = season or DEFAULT_VALUE_SEASON
    warnings: list[str] = []
    rows = _aggregate_rows(season)
    if not rows:
        warnings.append(f"No weekly stats available for {season}; regression board empty.")
        return RegressionBoard(
            season=season, baselines={}, sell_high=[], buy_low=[], warnings=warnings
        )

    baselines, flags = compute_td_regression(rows)
    sell = sorted(
        [f for f in flags if f.verdict == "SELL-HIGH"], key=lambda f: f.td_oe, reverse=True
    )[:top]
    buy = sorted([f for f in flags if f.verdict == "BUY-LOW"], key=lambda f: f.td_oe)[:top]
    return RegressionBoard(
        season=season,
        baselines={k: round(v, 5) for k, v in baselines.items()},
        sell_high=sell,
        buy_low=buy,
        warnings=warnings,
    )
