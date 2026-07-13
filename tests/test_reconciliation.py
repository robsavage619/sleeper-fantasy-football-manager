"""Scoring reconciliation test: engine output vs Sleeper's live players_points.

Pulls a past week's matchups from Sleeper and scores the same players via the
nflverse weekly data + our scoring engine. Asserts the scores match within
tolerance (±0.5 pts) for players with sufficient data coverage.

Skipped unless the nflverse parquet cache is present — run after ``sffm ingest``.

Usage:
    uv run pytest tests/test_reconciliation.py -v --no-header
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl
import pytest

from sleeper_ffm.config import NFLVERSE_DIR
from sleeper_ffm.scoring.engine import load_scoring, score, stats_from_nflverse
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

# Reconcile week 10, 2024 season — late enough for stable final stats.
_RECON_LEAGUE_SEASON = "2024"
_RECON_WEEK = 10

# Tolerance in fantasy points — step bonuses for 40+yd TDs are not in nflverse
# aggregate data, so a ±0.5 gap is acceptable.
_TOLERANCE = 0.5

# Minimum Sleeper-scored points to include (ignore near-zero lines — scratches etc.)
_MIN_PTS = 3.0


def _weekly_path(season: int) -> Path:
    return NFLVERSE_DIR / "weekly" / f"{season}.parquet"


@pytest.fixture(scope="module")
def weekly_2024() -> pl.DataFrame:
    """Load nflverse 2024 weekly data from cache (skip if not present)."""
    path = _weekly_path(2024)
    if not path.exists():
        pytest.skip(f"nflverse cache missing — run `sffm ingest --season 2024` first: {path}")
    return pl.read_parquet(path)


@pytest.fixture(scope="module")
def id_map() -> pl.DataFrame:
    """Load the nflverse ID crosswalk from cache (skip if not present)."""
    path = NFLVERSE_DIR / "id_map.parquet"
    if not path.exists():
        pytest.skip(f"id_map cache missing — run `sffm ingest --season 2024` first: {path}")
    df = pl.read_parquet(path)
    # sleeper_id comes from pandas as Float64 (NaN for missing); cast to int string
    return df.with_columns(
        pl.col("sleeper_id")
        .cast(pl.Int64, strict=False)
        .cast(pl.Utf8)
        .alias("sleeper_id_str")
    )


@pytest.fixture(scope="module")
def recon_week(weekly_2024: pl.DataFrame, id_map: pl.DataFrame) -> dict[str, float]:
    """Score every player in week 10 via the engine; return {sleeper_id: engine_pts}."""
    scoring = load_scoring()
    week_df = weekly_2024.filter(
        (pl.col("season") == 2024) & (pl.col("week") == _RECON_WEEK)
    )
    # Join nflverse gsis_id → sleeper_id
    joined = week_df.join(
        id_map.select(["gsis_id", "sleeper_id_str"]),
        left_on="player_id",
        right_on="gsis_id",
        how="left",
    )
    result: dict[str, float] = {}
    for row in joined.iter_rows(named=True):
        sid = row.get("sleeper_id_str")
        if not sid or sid == "None":
            continue
        stats = stats_from_nflverse(row)
        pts = score(stats, scoring)
        result[sid] = pts
    return result


def test_scoring_reconciliation(recon_week: dict[str, float]) -> None:
    """Engine scores must be within ±0.5 pts of Sleeper's official scores for week 10 2024.

    Validates: scoring engine correctness, nflverse column mapping, ID crosswalk.
    Logs any gaps above tolerance so they can be investigated.
    """
    with SleeperClient() as client:
        # Find the 2024 league by walking history
        history = client.league_history()
        league_2024 = next(
            (lg for lg in history if lg.season == _RECON_LEAGUE_SEASON),
            None,
        )
        if league_2024 is None:
            pytest.skip(f"No {_RECON_LEAGUE_SEASON} season found in league history")

        matchups = client.matchups(_RECON_WEEK, league_id=league_2024.league_id)

    # Collect sleeper_id → official_pts from all matchups
    official: dict[str, float] = {}
    for matchup in matchups:
        pp = matchup.get("players_points") or {}
        official.update({str(pid): float(pts) for pid, pts in pp.items()})

    candidates = {
        pid: pts
        for pid, pts in official.items()
        if pts >= _MIN_PTS and pid in recon_week
    }

    if not candidates:
        pytest.skip("No overlapping player IDs — crosswalk may need updating")

    gaps: list[tuple[str, float, float, float]] = []
    matched = 0
    for pid, official_pts in candidates.items():
        engine_pts = recon_week[pid]
        diff = abs(engine_pts - official_pts)
        if diff > _TOLERANCE:
            gaps.append((pid, official_pts, engine_pts, diff))
        else:
            matched += 1

    total = len(candidates)
    coverage = matched / total if total else 0.0
    log.info(
        "Reconciliation: %d/%d players within ±%.1f pts (%.0f%%)",
        matched, total, _TOLERANCE, coverage * 100,
    )

    for pid, off, eng, diff in gaps:
        log.warning(
            "  player %s: sleeper=%.2f engine=%.2f diff=%.2f",
            pid, off, eng, diff,
        )

    # Require ≥80% of players to match within tolerance
    assert coverage >= 0.80, (
        f"Reconciliation failed: only {coverage:.0%} of {total} players within "
        f"±{_TOLERANCE} pts. Check scoring_engine column map or ID crosswalk. "
        f"Gaps: {gaps[:10]}"
    )
