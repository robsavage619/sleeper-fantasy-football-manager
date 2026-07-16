"""Opponent-adjusted production — schedule-neutral fantasy points.

Raw weekly FP conflates two things: how good a player is, and how bad the defense he
faced was. ``schedule_strength.compute_dvp`` already scores every defense's DvP index
for the season (index > 1 = soft matchup, allowed more than league average; < 1 =
tough). This divides each player-week's FP by the DvP index of the defense actually
faced that week, producing a schedule-neutral figure — a "how much did the schedule
inflate/deflate this player's raw stat line" read that trend and mispricing signals
built on raw FP don't have.

The same season's DvP is used both to build the index and to deflate the games that
built it — a common, accepted lean (``schedule_strength`` takes the same approach for
SoS), not an independently-validated adjustment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import polars as pl

from sleeper_ffm.config import DEFAULT_VALUE_SEASON
from sleeper_ffm.model.schedule_strength import compute_dvp
from sleeper_ffm.model.valuation import SKILL_POSITIONS, score_weekly
from sleeper_ffm.nflverse.loader import load_id_map

log = logging.getLogger(__name__)

# Minimum games before a player's schedule-luck figure is trusted (small samples swing wildly).
_MIN_GAMES: int = 6


@dataclass
class OpponentAdjustedEntry:
    """One player's raw vs schedule-neutral production for a season."""

    player_id: str
    name: str
    position: str
    team: str
    games_played: int
    raw_fp: float
    adjusted_fp: float
    # raw - adjusted; +ve = softer-than-average schedule inflated the raw total
    schedule_luck: float
    note: str = ""


@dataclass
class OpponentAdjustedBoard:
    """Ranked schedule-luck surface for a season."""

    season: int
    softest_schedule: list[OpponentAdjustedEntry]  # raw stats most inflated by cushy matchups
    toughest_schedule: list[OpponentAdjustedEntry]  # raw stats most deflated by tough matchups
    warnings: list[str] = field(default_factory=list)


def opponent_adjusted_weekly(
    scored: pl.DataFrame, dvp: dict[tuple[str, str], float]
) -> pl.DataFrame:
    """Attach ``dvp_index`` and ``adj_fp`` (schedule-neutral FP) to every scored week.

    Args:
        scored: ``score_weekly`` output — needs ``fp_sffm``, ``opponent_team``, ``position``.
        dvp: DvP map from :func:`schedule_strength.compute_dvp`.

    Returns:
        ``scored`` with ``dvp_index`` (the divisor used, ``1.0`` for opponents without
        a DvP sample) and ``adj_fp`` (``fp_sffm / dvp_index``) columns added. Returns
        ``scored`` unchanged if required columns are missing.
    """
    needed = {"fp_sffm", "opponent_team", "position"}
    if scored.is_empty() or not needed.issubset(scored.columns):
        return scored
    if not dvp:
        return scored.with_columns(
            [pl.lit(1.0).alias("dvp_index"), pl.col("fp_sffm").alias("adj_fp")]
        )

    dvp_df = pl.DataFrame(
        [{"opponent_team": t, "position": p, "dvp_index": idx} for (t, p), idx in dvp.items()]
    )
    joined = scored.join(dvp_df, on=["opponent_team", "position"], how="left").with_columns(
        pl.col("dvp_index").fill_null(1.0)
    )
    return joined.with_columns((pl.col("fp_sffm") / pl.col("dvp_index")).alias("adj_fp"))


def build_opponent_adjusted(season: int | None = None, top: int = 15) -> OpponentAdjustedBoard:
    """Rank players by how much their schedule inflated or deflated their raw FP.

    Args:
        season: NFL season year (default: latest completed).
        top: Size of the ``softest_schedule`` / ``toughest_schedule`` shortlists.

    Returns:
        A :class:`OpponentAdjustedBoard`. Degrades to an empty board (with a warning)
        if weekly data is unavailable.
    """
    season = season or DEFAULT_VALUE_SEASON
    warnings: list[str] = []

    scored = score_weekly(seasons=[season])
    if scored.is_empty() or "opponent_team" not in scored.columns:
        warnings.append(f"No weekly nflverse data for {season}; opponent-adjusted board empty.")
        return OpponentAdjustedBoard(
            season=season, softest_schedule=[], toughest_schedule=[], warnings=warnings
        )

    dvp = compute_dvp(scored)
    if not dvp:
        warnings.append(f"No DvP could be computed for {season}; adjustment defaults to 1.0x.")
    adjusted = opponent_adjusted_weekly(scored, dvp)

    agg = (
        adjusted.filter(pl.col("position").is_in(list(SKILL_POSITIONS)))
        .group_by("player_id")
        .agg(
            [
                pl.col("fp_sffm").sum().alias("raw_fp"),
                pl.col("adj_fp").sum().alias("adjusted_fp"),
                pl.col("fp_sffm").len().alias("games_played"),
                pl.col("position").last().alias("position"),
                pl.col("player_display_name").last().alias("name"),
                pl.col("recent_team").last().alias("team"),
            ]
        )
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

    entries: list[OpponentAdjustedEntry] = []
    for row in agg.iter_rows(named=True):
        games = int(row["games_played"] or 0)
        if games < _MIN_GAMES:
            continue
        raw_fp = round(float(row["raw_fp"] or 0.0), 1)
        adjusted_fp = round(float(row["adjusted_fp"] or 0.0), 1)
        luck = round(raw_fp - adjusted_fp, 1)
        entries.append(
            OpponentAdjustedEntry(
                player_id=row.get("sleeper_id_str") or "",
                name=row.get("name") or "?",
                position=row["position"],
                team=row.get("team") or "FA",
                games_played=games,
                raw_fp=raw_fp,
                adjusted_fp=adjusted_fp,
                schedule_luck=luck,
                note=(
                    f"{'softer' if luck >= 0 else 'tougher'}-than-average schedule "
                    f"{'inflated' if luck >= 0 else 'deflated'} raw FP by {abs(luck):.1f}"
                ),
            )
        )

    softest = sorted(entries, key=lambda e: e.schedule_luck, reverse=True)[:top]
    toughest = sorted(entries, key=lambda e: e.schedule_luck)[:top]
    return OpponentAdjustedBoard(
        season=season, softest_schedule=softest, toughest_schedule=toughest, warnings=warnings
    )
