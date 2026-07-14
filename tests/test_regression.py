"""Tests for the TD-regression engine (pure logic — no network)."""

from __future__ import annotations

from sleeper_ffm.model.regression import compute_td_regression


def _row(sid: str, pos: str, yards: float, tds: float) -> dict:
    return {
        "sid": sid,
        "name": sid,
        "position": pos,
        "team": "X",
        "total_yards": yards,
        "total_tds": tds,
    }


def test_baseline_is_position_td_per_yard() -> None:
    rows = [_row("a", "WR", 1000.0, 8.0), _row("b", "WR", 1000.0, 2.0)]
    baselines, _ = compute_td_regression(rows)
    # 10 TDs / 2000 yards = 0.005 TD/yd.
    assert baselines["WR"] == 0.005


def test_sell_high_flag_for_lucky_scorer() -> None:
    # 'a' scores way above the 0.005 baseline for his yardage → sell high.
    rows = [
        _row("a", "WR", 1000.0, 12.0),
        _row("b", "WR", 1000.0, 2.0),
        _row("c", "WR", 1000.0, 2.0),
    ]
    _, flags = compute_td_regression(rows)
    a = next(f for f in flags if f.player_id == "a")
    assert a.verdict == "SELL-HIGH"
    assert a.td_oe > 0


def test_buy_low_flag_for_unlucky_scorer() -> None:
    rows = [
        _row("a", "WR", 1000.0, 12.0),
        _row("b", "WR", 1000.0, 0.0),
        _row("c", "WR", 1000.0, 12.0),
    ]
    _, flags = compute_td_regression(rows)
    b = next(f for f in flags if f.player_id == "b")
    assert b.verdict == "BUY-LOW"
    assert b.td_oe < 0


def test_low_volume_players_excluded() -> None:
    rows = [_row("a", "WR", 100.0, 5.0), _row("b", "WR", 1000.0, 3.0), _row("c", "WR", 1000.0, 3.0)]
    _, flags = compute_td_regression(rows, min_yards=250)
    assert all(f.player_id != "a" for f in flags)


def test_neutral_when_tds_match_volume() -> None:
    rows = [_row("a", "WR", 1000.0, 5.0), _row("b", "WR", 1000.0, 5.0)]
    _, flags = compute_td_regression(rows)
    assert all(f.verdict == "NEUTRAL" for f in flags)
