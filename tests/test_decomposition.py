"""S1 decomposition tests (synthetic frames — no network, no cached parquet)."""

from __future__ import annotations

import polars as pl
import pytest

import sleeper_ffm.model.research.decomposition as decomp


def _weekly_row(pid: str, season: int, week: int, **stats: float) -> dict[str, object]:
    row: dict[str, object] = {
        "player_id": pid,
        "player_display_name": pid,
        "position": "WR",
        "recent_team": "AAA",
        "season": season,
        "week": week,
        "season_type": "REG",
        "receptions": 0.0,
        "receiving_yards": 0.0,
        "receiving_tds": 0.0,
        "carries": 0.0,
        "rushing_yards": 0.0,
        "rushing_tds": 0.0,
        "targets": 0.0,
    }
    row.update(stats)
    return row


def test_bonus_isolates_threshold_points(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 100-yard game must score above a 99-yard game by exactly the bonus."""
    weekly = pl.DataFrame(
        [
            _weekly_row("under", 2020, 1, receptions=5.0, receiving_yards=99.0),
            _weekly_row("over", 2020, 1, receptions=5.0, receiving_yards=100.0),
        ]
    )
    monkeypatch.setattr(decomp, "load_weekly", lambda seasons=None: weekly)

    scored = decomp.score_weekly_variants()
    under = scored.filter(pl.col("player_id") == "under").row(0, named=True)
    over = scored.filter(pl.col("player_id") == "over").row(0, named=True)

    assert under["fp_bonus"] == 0.0
    assert over["fp_bonus"] == pytest.approx(2.5)
    # The bonus-free variant must be blind to the threshold entirely.
    assert over["fp_base"] - under["fp_base"] == pytest.approx(0.1)


def test_long_td_bonus_counts_only_40_plus_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    pbp = pl.DataFrame(
        [
            # 45-yard receiving TD — counts for receiver and passer.
            {
                "season": 2020,
                "season_type": "REG",
                "touchdown": 1,
                "yards_gained": 45,
                "pass_touchdown": 1,
                "rush_touchdown": 0,
                "receiver_player_id": "wr1",
                "rusher_player_id": None,
                "passer_player_id": "qb1",
            },
            # 39-yard TD — below threshold, must not count.
            {
                "season": 2020,
                "season_type": "REG",
                "touchdown": 1,
                "yards_gained": 39,
                "pass_touchdown": 1,
                "rush_touchdown": 0,
                "receiver_player_id": "wr1",
                "rusher_player_id": None,
                "passer_player_id": "qb1",
            },
            # 60-yard run that is not a touchdown — must not count.
            {
                "season": 2020,
                "season_type": "REG",
                "touchdown": 0,
                "yards_gained": 60,
                "pass_touchdown": 0,
                "rush_touchdown": 0,
                "receiver_player_id": None,
                "rusher_player_id": "rb1",
                "passer_player_id": None,
            },
            # Playoff long TD — regular season only.
            {
                "season": 2020,
                "season_type": "POST",
                "touchdown": 1,
                "yards_gained": 70,
                "pass_touchdown": 0,
                "rush_touchdown": 1,
                "receiver_player_id": None,
                "rusher_player_id": "rb1",
                "passer_player_id": None,
            },
        ]
    )
    monkeypatch.setattr(decomp, "load_pbp", lambda seasons=None: pbp)

    counts = decomp.long_td_bonuses([2020])
    as_dict = {r["player_id"]: r["td40"] for r in counts.iter_rows(named=True)}
    assert as_dict == {"wr1": 1, "qb1": 1}


def test_long_tds_raise_bonus_totals(monkeypatch: pytest.MonkeyPatch) -> None:
    """The aggregate path misses long TDs; crediting them must raise bonus points."""
    weekly = pl.DataFrame(
        [
            _weekly_row("wr1", 2020, w, receptions=4.0, receiving_yards=60.0, receiving_tds=1.0)
            for w in range(1, 9)
        ]
    )
    pbp = pl.DataFrame(
        [
            {
                "season": 2020,
                "season_type": "REG",
                "touchdown": 1,
                "yards_gained": 55,
                "pass_touchdown": 1,
                "rush_touchdown": 0,
                "receiver_player_id": "wr1",
                "rusher_player_id": None,
                "passer_player_id": "qb1",
            }
        ]
    )
    monkeypatch.setattr(decomp, "load_weekly", lambda seasons=None: weekly)
    monkeypatch.setattr(decomp, "load_pbp", lambda seasons=None: pbp)

    without = decomp.player_season_decomposition(include_long_tds=False)
    with_long = decomp.player_season_decomposition(include_long_tds=True)

    base = without.filter(pl.col("player_id") == "wr1").row(0, named=True)
    credited = with_long.filter(pl.col("player_id") == "wr1").row(0, named=True)

    assert credited["fp_bonus"] - base["fp_bonus"] == pytest.approx(decomp.TD40_POINTS)
    assert credited["td40"] == 1


def test_residual_is_centred_within_position(monkeypatch: pytest.MonkeyPatch) -> None:
    """Residuals must have zero mean per position, else 'above expected' means nothing."""
    rows = []
    for i, yards in enumerate([40.0, 60.0, 80.0, 100.0, 120.0, 140.0]):
        for week in range(1, 9):
            rows.append(_weekly_row(f"p{i}", 2020, week, receptions=5.0, receiving_yards=yards))
    monkeypatch.setattr(decomp, "load_weekly", lambda seasons=None: pl.DataFrame(rows))

    df = decomp.player_season_decomposition(include_long_tds=False)
    assert df["bonus_residual"].mean() == pytest.approx(0.0, abs=1e-9)


def test_stickiness_pairs_consecutive_seasons(monkeypatch: pytest.MonkeyPatch) -> None:
    """A profile each player repeats exactly must come back as r = 1."""
    df = pl.DataFrame(
        {
            "player_id": ["a", "a", "b", "b", "c", "c"],
            "season": [2020, 2021] * 3,
            "position": ["WR"] * 6,
            "bonus_residual": [1.0, 1.0, 0.0, 0.0, -1.0, -1.0],
        }
    )
    results = decomp.stickiness(df, metrics=("bonus_residual",), by_position=False)
    assert len(results) == 1
    assert results[0].n_pairs == 3
    assert results[0].correlation == pytest.approx(1.0)


def test_empty_inputs_return_empty_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(decomp, "load_weekly", lambda seasons=None: pl.DataFrame())
    assert decomp.player_season_decomposition().is_empty()
    assert decomp.stickiness(pl.DataFrame()) == []
