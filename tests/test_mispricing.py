"""Tests for the scoring-leverage mispricing engine (pure logic — no network)."""

from __future__ import annotations

from unittest.mock import patch

import polars as pl

from sleeper_ffm.model.mispricing import STANDARD_PPR, build_mispricing


def _totals(rows: list[dict]) -> pl.DataFrame:
    """Build a frame shaped like ``compute_season_totals`` output."""
    return pl.DataFrame(
        rows,
        schema={
            "gsis_id": pl.Utf8,
            "season": pl.Int64,
            "position": pl.Utf8,
            "season_fp": pl.Float64,
            "games_played": pl.Float64,
            "name": pl.Utf8,
            "team": pl.Utf8,
            "sleeper_id_str": pl.Utf8,
        },
    )


def _wr(gsis: str, sid: str, fp: float) -> dict:
    return {
        "gsis_id": gsis,
        "season": 2025,
        "position": "WR",
        "season_fp": fp,
        "games_played": 12.0,
        "name": f"WR {gsis}",
        "team": "NYJ",
        "sleeper_id_str": sid,
    }


def _run(our_fp: dict[str, float], generic_fp: float, market: dict | None = None):
    """Run build_mispricing with WRs sharing one generic FP and varied league FP."""
    our = _totals([_wr(g, g.upper(), fp) for g, fp in our_fp.items()])
    generic = _totals([_wr(g, g.upper(), generic_fp) for g in our_fp])

    def fake_totals(*_args, **kwargs):
        return generic if "scoring" in kwargs else our

    with (
        patch("sleeper_ffm.model.mispricing.compute_season_totals", side_effect=fake_totals),
        patch("sleeper_ffm.model.mispricing.market_anchor", return_value=market or {}),
    ):
        return build_mispricing(seasons=[2025], min_games=6)


def test_buy_when_league_scoring_favors_player() -> None:
    board = _run({"a": 240.0, "b": 200.0, "c": 200.0, "d": 200.0}, generic_fp=200.0)
    by_name = {e.player_id: e for e in board.entries}
    assert by_name["A"].edge_pct == 20.0
    assert by_name["A"].verdict == "BUY"
    assert board.buys[0].player_id == "A"


def test_sell_when_league_scoring_penalizes_player() -> None:
    board = _run({"a": 160.0, "b": 200.0, "c": 200.0, "d": 200.0}, generic_fp=200.0)
    a = next(e for e in board.entries if e.player_id == "A")
    assert a.edge_pct == -20.0
    assert a.verdict == "SELL"
    assert board.sells[0].player_id == "A"


def test_league_wide_level_shift_cancels() -> None:
    # Uniform 1.5x (e.g. 6-pt vs 4-pt TDs across the board) must not create edge.
    flat = _run({"a": 1.5 * 240, "b": 1.5 * 200, "c": 1.5 * 200, "d": 1.5 * 200}, generic_fp=200.0)
    a = next(e for e in flat.entries if e.player_id == "A")
    assert a.edge_pct == 20.0  # identical to the un-shifted case


def test_value_gap_uses_market_when_available() -> None:
    board = _run(
        {"a": 240.0, "b": 200.0, "c": 200.0, "d": 200.0},
        generic_fp=200.0,
        market={"A": 10000.0},
    )
    a = next(e for e in board.entries if e.player_id == "A")
    assert a.market_value == 660.0  # 10000 * FC_TO_DYNASTY_SCALE (0.066)
    assert a.value_gap == 132.0  # 660 * 20%
    b = next(e for e in board.entries if e.player_id == "B")
    assert b.market_value is None


def test_below_min_games_excluded() -> None:
    our = _totals(
        [
            {**_wr("a", "A", 240.0), "games_played": 3.0},
            _wr("b", "B", 200.0),
            _wr("c", "C", 200.0),
        ]
    )
    generic = _totals([_wr(g, g.upper(), 200.0) for g in ("a", "b", "c")])

    def fake_totals(*_args, **kwargs):
        return generic if "scoring" in kwargs else our

    with (
        patch("sleeper_ffm.model.mispricing.compute_season_totals", side_effect=fake_totals),
        patch("sleeper_ffm.model.mispricing.market_anchor", return_value={}),
    ):
        board = build_mispricing(seasons=[2025], min_games=6)
    assert all(e.player_id != "A" for e in board.entries)


def test_empty_data_returns_empty_board() -> None:
    empty = _totals([])
    with (
        patch("sleeper_ffm.model.mispricing.compute_season_totals", return_value=empty),
        patch("sleeper_ffm.model.mispricing.market_anchor", return_value={}),
    ):
        board = build_mispricing(seasons=[2025])
    assert board.entries == []
    assert board.warnings


def test_standard_ppr_has_no_bonus_keys() -> None:
    assert not any(k.startswith("bonus_") for k in STANDARD_PPR)
