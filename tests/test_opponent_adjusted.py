"""Tests for opponent-adjusted (schedule-neutral) production (pure logic — no network)."""

from __future__ import annotations

import polars as pl

from sleeper_ffm.model.opponent_adjusted import opponent_adjusted_weekly


def _scored(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "player_id": pl.Utf8,
            "player_display_name": pl.Utf8,
            "recent_team": pl.Utf8,
            "season": pl.Int64,
            "week": pl.Int64,
            "position": pl.Utf8,
            "opponent_team": pl.Utf8,
            "fp_sffm": pl.Float64,
        },
    )


def _row(pid: str, opp: str, pos: str, fp: float) -> dict:
    return {
        "player_id": pid,
        "player_display_name": pid,
        "recent_team": "X",
        "season": 2025,
        "week": 1,
        "position": pos,
        "opponent_team": opp,
        "fp_sffm": fp,
    }


def test_soft_matchup_deflates_adjusted_fp() -> None:
    # SOFT allows 1.5x league average -> a game against SOFT reads as inflated raw stats.
    scored = _scored([_row("a", "SOFT", "RB", 30.0)])
    dvp = {("SOFT", "RB"): 1.5}
    out = opponent_adjusted_weekly(scored, dvp)
    row = out.row(0, named=True)
    assert row["dvp_index"] == 1.5
    assert row["adj_fp"] == 20.0  # 30 / 1.5


def test_tough_matchup_inflates_adjusted_fp() -> None:
    scored = _scored([_row("a", "TOUGH", "RB", 10.0)])
    dvp = {("TOUGH", "RB"): 0.5}
    out = opponent_adjusted_weekly(scored, dvp)
    row = out.row(0, named=True)
    assert row["adj_fp"] == 20.0  # 10 / 0.5


def test_unknown_opponent_defaults_to_neutral() -> None:
    scored = _scored([_row("a", "MYSTERY", "RB", 15.0)])
    out = opponent_adjusted_weekly(scored, {("SOFT", "RB"): 1.5})
    row = out.row(0, named=True)
    assert row["dvp_index"] == 1.0
    assert row["adj_fp"] == 15.0


def test_empty_dvp_map_is_neutral_for_everyone() -> None:
    scored = _scored([_row("a", "SOFT", "RB", 15.0)])
    out = opponent_adjusted_weekly(scored, {})
    row = out.row(0, named=True)
    assert row["dvp_index"] == 1.0
    assert row["adj_fp"] == 15.0


def test_missing_columns_returns_unchanged() -> None:
    bare = pl.DataFrame({"foo": [1]})
    assert opponent_adjusted_weekly(bare, {("SOFT", "RB"): 1.5}) is bare
