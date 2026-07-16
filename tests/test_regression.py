"""Tests for the TD-regression engine (pure logic — no network)."""

from __future__ import annotations

import polars as pl

from sleeper_ffm.model.regression import compute_redzone_td_regression, compute_td_regression


def _row(
    sid: str,
    pos: str,
    yards: float,
    tds: float,
    age: float | None = None,
    gsis_id: str | None = None,
) -> dict:
    return {
        "sid": sid,
        "gsis_id": sid if gsis_id is None else gsis_id,
        "name": sid,
        "position": pos,
        "team": "X",
        "total_yards": yards,
        "total_tds": tds,
        "age": age,
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


def test_age_decline_overrides_buy_low_for_aging_veteran() -> None:
    # Same unlucky-scoring shape as test_buy_low_flag_for_unlucky_scorer, but 'b' is a
    # 41yo QB (peak 29 + 8yr decline buffer = 37) — should read as decline, not luck.
    rows = [
        _row("a", "QB", 1000.0, 12.0),
        _row("b", "QB", 1000.0, 0.0, age=41.0),
        _row("c", "QB", 1000.0, 12.0),
    ]
    _, flags = compute_td_regression(rows)
    b = next(f for f in flags if f.player_id == "b")
    assert b.verdict == "AGE-DECLINE"
    assert b.td_oe < 0


def test_buy_low_still_flags_unlucky_player_in_prime() -> None:
    rows = [
        _row("a", "QB", 1000.0, 12.0),
        _row("b", "QB", 1000.0, 0.0, age=26.0),
        _row("c", "QB", 1000.0, 12.0),
    ]
    _, flags = compute_td_regression(rows)
    b = next(f for f in flags if f.player_id == "b")
    assert b.verdict == "BUY-LOW"


# --- red-zone-opportunity TD model (v2) -----------------------------------


def _play_values(rows: list[tuple[str, str, bool, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "player_id": pl.Utf8,
            "kind": pl.Utf8,
            "is_redzone": pl.Boolean,
            "fp": pl.Float64,
            "touchdown": pl.Float64,
        },
        orient="row",
    )


def test_redzone_td_regression_prices_by_opportunity_not_yardage() -> None:
    # 'lucky' scores 3 TDs on 3 red-zone targets. League-wide (incl. 'field's 17
    # targets, 2 TDs) the red-zone rate is 5/20 = 0.25 -> expected = 3*0.25 = 0.75,
    # td_oe = 3 - 0.75 = 2.25 >= the 2.0 flag threshold -> SELL-HIGH.
    lucky_plays = [("gsis-lucky", "target", True, 7.0, 1.0)] * 3
    field_plays = [("gsis-field", "target", True, 1.0, 0.0)] * 15 + [
        ("gsis-field", "target", True, 7.0, 1.0)
    ] * 2
    play_values = _play_values(lucky_plays + field_plays)
    rows = [_row("lucky", "WR", 300.0, 3.0, gsis_id="gsis-lucky")]
    position_by_player = {"gsis-lucky": "WR", "gsis-field": "WR"}
    rates, flags = compute_redzone_td_regression(
        rows, play_values, position_by_player, min_yards=250
    )
    lucky = next(f for f in flags if f.player_id == "lucky")
    assert rates["WR"]["rz_targets"] == 0.25
    assert lucky.expected_tds == round(0.75, 1)  # 3 rz targets * 0.25 league rate
    assert lucky.verdict == "SELL-HIGH"


def test_redzone_td_regression_skips_player_without_gsis_id() -> None:
    play_values = _play_values([("gsis-a", "target", True, 7.0, 1.0)])
    rows = [_row("a", "WR", 300.0, 1.0, gsis_id="")]
    _, flags = compute_redzone_td_regression(rows, play_values, {"gsis-a": "WR"}, min_yards=250)
    assert flags == []
