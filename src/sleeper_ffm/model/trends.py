"""Target-share and FPAR trend signals from nflverse weekly data.

Surfaces breakout and decline candidates by comparing a player's last
N weeks against their season average for target share and scored
fantasy points above replacement (fp_sffm).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

from sleeper_ffm.nflverse.loader import load_id_map, load_weekly
from sleeper_ffm.scoring.engine import load_scoring, score, stats_from_nflverse

log = logging.getLogger(__name__)

SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}


@dataclass
class TrendSignal:
    """Trend signal for a single player."""

    player_id: str  # Sleeper ID (string integer)
    gsis_id: str  # nflverse gsis_id
    name: str
    position: str
    team: str
    age: float
    target_share_delta: float | None  # recent - season avg target share (WR/TE)
    snap_share_delta: float | None  # recent - season avg snap share (always None currently)
    fpar_delta: float | None  # recent - season avg fp_sffm
    signal_strength: float  # abs(target_share_delta) or abs(snap_share_delta), else 0
    direction: str  # "RISING" | "FALLING" | "FLAT"
    weeks_analyzed: int  # total season games used


def compute_trends(
    seasons: list[int] | None = None,
    n_recent_weeks: int = 4,
) -> list[TrendSignal]:
    """Compute target-share and FPAR trend signals from nflverse weekly data.

    Scores each player-week under league rules, then compares the last
    ``n_recent_weeks`` distinct regular-season weeks against the full season
    average. Only players with >= 8 season games and >= n_recent_weeks recent
    games are included.

    Args:
        seasons: Seasons to analyze. Defaults to [2024].
        n_recent_weeks: Number of recent weeks to treat as the trend window.

    Returns:
        TrendSignals sorted by signal_strength descending.
    """
    seasons = seasons or [2024]

    weekly = load_weekly(seasons=seasons)
    if weekly.is_empty():
        log.debug("compute_trends: no weekly data loaded, returning empty")
        return []

    # Filter to regular season skill positions
    filtered = weekly.filter(
        pl.col("season_type").eq("REG")
        & pl.col("position").is_in(list(SKILL_POSITIONS))
    )
    if filtered.is_empty():
        log.debug("compute_trends: no skill-position REG rows after filter")
        return []

    # Score each row with league rules
    try:
        scoring = load_scoring()
    except FileNotFoundError:
        log.warning("compute_trends: league_settings.json not found, cannot score")
        return []

    fp_values: list[float] = []
    for row in filtered.iter_rows(named=True):
        fp_values.append(score(stats_from_nflverse(row), scoring))
    filtered = filtered.with_columns(pl.Series("fp_sffm", fp_values, dtype=pl.Float64))

    # Build gsis_id → {sleeper_id, age} lookup from id_map
    gsis_to_sleeper: dict[str, str] = {}
    gsis_to_age: dict[str, float] = {}
    try:
        id_map = load_id_map()
        for row in (
            id_map.filter(
                pl.col("gsis_id").str.starts_with("00-")
                & pl.col("sleeper_id").is_not_null()
            )
            .select(["gsis_id", "sleeper_id", "age"])
            .iter_rows(named=True)
        ):
            gid = row["gsis_id"]
            sid = row["sleeper_id"]
            if gid and sid is not None:
                gsis_to_sleeper[gid] = str(int(sid))
            age_val = row["age"]
            if gid and age_val is not None:
                gsis_to_age[gid] = float(age_val)
    except Exception:
        log.debug("compute_trends: id_map unavailable, sleeper_ids will fall back to gsis_id")

    # Determine the N most recent distinct weeks in the filtered data
    all_weeks: list[int] = sorted(filtered["week"].unique().to_list())
    recent_week_set: set[int] = (
        set(all_weeks[-n_recent_weeks:]) if len(all_weeks) >= n_recent_weeks else set(all_weeks)
    )

    # Detect available columns
    has_target_share = "target_share" in filtered.columns

    if not has_target_share:
        log.debug("compute_trends: target_share column not found, signal_strength will be 0")

    # Season-level aggregation (all REG weeks)
    season_agg_exprs = [
        pl.len().alias("season_games"),
        pl.col("fp_sffm").mean().alias("season_fp_avg"),
        pl.col("player_display_name").first().alias("name"),
        pl.col("recent_team").last().alias("team"),
    ]
    if has_target_share:
        season_agg_exprs.append(pl.col("target_share").mean().alias("season_ts_avg"))

    season_agg = filtered.group_by(["player_id", "position"]).agg(season_agg_exprs)

    # Recent-window aggregation
    recent_df = filtered.filter(pl.col("week").is_in(list(recent_week_set)))
    recent_agg_exprs = [
        pl.len().alias("recent_games"),
        pl.col("fp_sffm").mean().alias("recent_fp_avg"),
    ]
    if has_target_share:
        recent_agg_exprs.append(pl.col("target_share").mean().alias("recent_ts_avg"))

    recent_agg = recent_df.group_by("player_id").agg(recent_agg_exprs)

    # Join and gate on minimum sample size
    joined = (
        season_agg.join(recent_agg, on="player_id", how="left")
        .filter(
            pl.col("season_games").ge(8)
            & pl.col("recent_games").ge(n_recent_weeks)
        )
    )

    signals: list[TrendSignal] = []
    for row in joined.iter_rows(named=True):
        gsis_id: str = row["player_id"] or ""
        sleeper_id = gsis_to_sleeper.get(gsis_id, gsis_id)
        age = gsis_to_age.get(gsis_id, 0.0)

        fpar_delta: float | None = None
        ts_delta: float | None = None
        snap_delta: float | None = None  # no snap column in current nflverse weekly

        s_fp = row.get("season_fp_avg")
        r_fp = row.get("recent_fp_avg")
        if s_fp is not None and r_fp is not None:
            fpar_delta = r_fp - s_fp

        if has_target_share:
            s_ts = row.get("season_ts_avg")
            r_ts = row.get("recent_ts_avg")
            if s_ts is not None and r_ts is not None:
                ts_delta = r_ts - s_ts

        # Signal strength: target share delta preferred; fallback to snap (unavailable)
        if ts_delta is not None:
            signal_strength = abs(ts_delta)
        elif snap_delta is not None:
            signal_strength = abs(snap_delta)
        else:
            signal_strength = 0.0

        # Direction: RISING if FPAR > +3 or target share > +0.03, FALLING if inverse
        rising = (fpar_delta is not None and fpar_delta > 3.0) or (
            ts_delta is not None and ts_delta > 0.03
        )
        falling = (fpar_delta is not None and fpar_delta < -3.0) or (
            ts_delta is not None and ts_delta < -0.03
        )
        if rising:
            direction = "RISING"
        elif falling:
            direction = "FALLING"
        else:
            direction = "FLAT"

        signals.append(
            TrendSignal(
                player_id=sleeper_id,
                gsis_id=gsis_id,
                name=row.get("name") or "",
                position=row.get("position") or "",
                team=row.get("team") or "",
                age=age,
                target_share_delta=ts_delta,
                snap_share_delta=snap_delta,
                fpar_delta=fpar_delta,
                signal_strength=signal_strength,
                direction=direction,
                weeks_analyzed=int(row.get("season_games") or 0),
            )
        )

    return sorted(signals, key=lambda s: s.signal_strength, reverse=True)
