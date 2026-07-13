"""Keyless college box-score aggregation — hermetic unit tests (no network)."""

from __future__ import annotations

import polars as pl

from sleeper_ffm.college import cfb_box


def _frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows)


def test_parse_comp_att_sums_fractions() -> None:
    frame = _frame(
        [
            {"completions/passingAttempts": "22/31"},
            {"completions/passingAttempts": "18/27"},
            {"completions/passingAttempts": None},
        ]
    )
    assert cfb_box._parse_comp_att(frame) == (40, 58)


def test_season_row_receiving_and_rushing() -> None:
    sub = _frame(
        [
            {
                "category": "receiving",
                "receptions": 8,
                "receivingYards": 120,
                "receivingTouchdowns": 1,
            },
            {
                "category": "receiving",
                "receptions": 5,
                "receivingYards": 60,
                "receivingTouchdowns": 0,
            },
            {
                "category": "rushing",
                "rushingAttempts": 12,
                "rushingYards": 90,
                "rushingTouchdowns": 1,
            },
        ]
    )
    row = cfb_box._season_row(sub, 2025)
    assert row is not None
    assert row["receiving"] == {
        "games": 2,
        "receptions": 13,
        "yards": 180,
        "touchdowns": 1,
        "ypr": round(180 / 13, 1),
    }
    assert row["rushing"]["carries"] == 12
    assert row["rushing"]["ypc"] == 7.5


def test_season_row_drops_zero_carry_rushing_noise() -> None:
    sub = _frame(
        [
            {
                "category": "receiving",
                "receptions": 6,
                "receivingYards": 90,
                "receivingTouchdowns": 1,
            },
            {
                "category": "rushing",
                "rushingAttempts": 0,
                "rushingYards": 6,
                "rushingTouchdowns": 0,
            },
        ]
    )
    row = cfb_box._season_row(sub, 2025)
    assert row is not None
    assert "receiving" in row
    assert "rushing" not in row  # 0-carry stray row is not a rushing role


def test_season_row_passing() -> None:
    sub = _frame(
        [
            {
                "category": "passing",
                "completions/passingAttempts": "25/34",
                "passingYards": 310,
                "passingTouchdowns": 3,
                "interceptions": 1,
            }
        ]
    )
    row = cfb_box._season_row(sub, 2025)
    assert row is not None
    p = row["passing"]
    assert p["completions"] == 25
    assert p["attempts"] == 34
    assert p["yards"] == 310
    assert p["touchdowns"] == 3
    assert p["interceptions"] == 1


def test_season_row_empty_returns_none() -> None:
    sub = _frame([{"category": "defensive", "receptions": None}])
    assert cfb_box._season_row(sub, 2025) is None
