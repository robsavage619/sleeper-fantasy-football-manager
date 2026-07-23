"""Long-touchdown bonus crediting (no network — pbp and weekly are monkeypatched)."""

from __future__ import annotations

import polars as pl
import pytest

import sleeper_ffm.model.valuation as val
from sleeper_ffm.scoring.engine import score, stats_from_nflverse


def _scoring() -> dict[str, float]:
    return {"rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0, "rec_td_40p": 2.5, "rush_td_40p": 2.5}


def test_long_td_key_is_paid_when_supplied() -> None:
    """A source that supplies the count must have it scored."""
    row = {"receptions": 3, "receiving_yards": 70, "receiving_tds": 1, "rec_td_40p": 1}
    assert score(stats_from_nflverse(row), _scoring()) == pytest.approx(3 + 7.0 + 6.0 + 2.5)


def test_absent_long_td_key_scores_zero_not_error() -> None:
    """Historical behaviour: a source without the column simply earns no bonus."""
    row = {"receptions": 3, "receiving_yards": 70, "receiving_tds": 1}
    assert score(stats_from_nflverse(row), _scoring()) == pytest.approx(3 + 7.0 + 6.0)


def test_long_td_counts_splits_by_scoring_type(monkeypatch: pytest.MonkeyPatch) -> None:
    pbp = pl.DataFrame(
        [
            {
                "season": 2024,
                "week": 1,
                "season_type": "REG",
                "touchdown": 1,
                "yards_gained": 55,
                "pass_touchdown": 1,
                "rush_touchdown": 0,
                "receiver_player_id": "wr1",
                "rusher_player_id": None,
                "passer_player_id": "qb1",
            },
            {
                "season": 2024,
                "week": 1,
                "season_type": "REG",
                "touchdown": 1,
                "yards_gained": 41,
                "pass_touchdown": 0,
                "rush_touchdown": 1,
                "receiver_player_id": None,
                "rusher_player_id": "rb1",
                "passer_player_id": None,
            },
            {
                "season": 2024,
                "week": 1,
                "season_type": "REG",
                "touchdown": 1,
                "yards_gained": 20,
                "pass_touchdown": 1,
                "rush_touchdown": 0,
                "receiver_player_id": "wr1",
                "rusher_player_id": None,
                "passer_player_id": "qb1",
            },
        ]
    )
    monkeypatch.setattr(val, "load_pbp", lambda seasons=None: pbp)
    val.long_td_counts.cache_clear()

    counts = val.long_td_counts([2024])
    by_player = {r["player_id"]: r for r in counts.iter_rows(named=True)}
    assert by_player["wr1"]["rec_td_40p"] == 1
    assert by_player["qb1"]["pass_td_40p"] == 1
    assert by_player["rb1"]["rush_td_40p"] == 1
    # The 20-yard score must not be counted for anyone.
    assert by_player["wr1"]["pass_td_40p"] == 0


def test_seasons_without_pbp_coverage_score_without_bonuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2014-15 predate pbp coverage; they must degrade quietly, not crash or invent."""
    val.long_td_counts.cache_clear()
    monkeypatch.setattr(
        val, "load_pbp", lambda seasons=None: (_ for _ in ()).throw(AssertionError("no fetch"))
    )
    counts = val.long_td_counts([2014, 2015])
    assert counts.is_empty()


def test_score_weekly_attaches_bonus_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every scored row carries the three bonus columns, zero-filled where absent."""
    weekly = pl.DataFrame(
        [
            {
                "player_id": "wr1",
                "player_display_name": "WR One",
                "position": "WR",
                "recent_team": "AAA",
                "season": 2024,
                "week": 1,
                "season_type": "REG",
                "receptions": 4,
                "receiving_yards": 80,
                "receiving_tds": 1,
            }
        ]
    )
    monkeypatch.setattr(val, "load_weekly", lambda seasons=None: weekly)
    monkeypatch.setattr(val, "long_td_counts", lambda seasons: val._empty_long_td_frame())

    scored = val.score_weekly(seasons=[2024])
    for col in ("rec_td_40p", "rush_td_40p", "pass_td_40p"):
        assert col in scored.columns
        assert scored[col].to_list() == [0]
