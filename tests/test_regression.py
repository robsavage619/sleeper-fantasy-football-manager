"""Tests for the TD-regression engine (pure logic — no network)."""

from __future__ import annotations

import polars as pl

from sleeper_ffm.model.regression import compute_td_regression, compute_yardline_td_regression


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


# --- yard-line-opportunity TD model (v2) -----------------------------------


def _play_values(rows: list[tuple[str, str, str, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "player_id": pl.Utf8,
            "kind": pl.Utf8,
            "yardline_bin": pl.Utf8,
            "fp": pl.Float64,
            "touchdown": pl.Float64,
        },
        orient="row",
    )


def test_yardline_td_regression_prices_by_opportunity_not_yardage() -> None:
    # 'lucky' scores 3 TDs on 3 goal-line targets. League-wide (incl. 'field's 17
    # targets, 2 TDs) the 1-5 rate is 5/20 = 0.25 -> expected = 3*0.25 = 0.75,
    # td_oe = 3 - 0.75 = 2.25 >= the 2.0 flag threshold -> SELL-HIGH.
    lucky_plays = [("gsis-lucky", "target", "1-5", 7.0, 1.0)] * 3
    field_plays = [("gsis-field", "target", "1-5", 1.0, 0.0)] * 15 + [
        ("gsis-field", "target", "1-5", 7.0, 1.0)
    ] * 2
    play_values = _play_values(lucky_plays + field_plays)
    rows = [_row("lucky", "WR", 300.0, 3.0, gsis_id="gsis-lucky")]
    position_by_player = {"gsis-lucky": "WR", "gsis-field": "WR"}
    rates, flags = compute_yardline_td_regression(
        rows, play_values, position_by_player, min_yards=250
    )
    lucky = next(f for f in flags if f.player_id == "lucky")
    assert rates["WR"]["1-5_targets"] == 0.25
    assert lucky.expected_tds == round(0.75, 1)  # 3 goal-line targets * 0.25 league rate
    assert lucky.verdict == "SELL-HIGH"


def test_yardline_td_regression_separates_goal_line_from_red_zone_edge() -> None:
    # Both players take 4 red-zone targets and score 2 TDs on them, so the old binary
    # bucket priced them identically. 'goalline' takes his from inside the 5, where the
    # league converts 1 in 2; 'edge' from the 11-20, where it converts 1 in 8.
    def noise(yl_bin: str, misses: int, scores: int) -> list[tuple[str, str, str, float, float]]:
        return [("gsis-noise", "target", yl_bin, 1.0, 0.0)] * misses + [
            ("gsis-noise", "target", yl_bin, 7.0, 1.0)
        ] * scores

    def player(gsis: str, yl_bin: str) -> list[tuple[str, str, str, float, float]]:
        return [(gsis, "target", yl_bin, 1.0, 0.0)] * 2 + [(gsis, "target", yl_bin, 7.0, 1.0)] * 2

    plays = (
        # 1-5 league-wide: 12 targets, 6 TDs = 0.5. 11-20: 32 targets, 4 TDs = 0.125.
        noise("1-5", 4, 4)
        + noise("11-20", 26, 2)
        + player("gsis-goalline", "1-5")
        + player("gsis-edge", "11-20")
    )
    rows = [
        _row("goalline", "WR", 300.0, 2.0, gsis_id="gsis-goalline"),
        _row("edge", "WR", 300.0, 2.0, gsis_id="gsis-edge"),
    ]
    positions = {"gsis-noise": "WR", "gsis-goalline": "WR", "gsis-edge": "WR"}
    rates, flags = compute_yardline_td_regression(
        rows, _play_values(plays), positions, min_yards=250
    )
    assert (rates["WR"]["1-5_targets"], rates["WR"]["11-20_targets"]) == (0.5, 0.125)
    by_id = {f.player_id: f for f in flags}
    assert by_id["goalline"].expected_tds == 2.0  # 4 * 0.5 — his 2 TDs were the going rate
    assert by_id["edge"].expected_tds == 0.5  # 4 * 0.125 — the same 2 TDs ran hot
    assert by_id["goalline"].td_oe == 0.0
    assert by_id["edge"].td_oe == 1.5


def test_yardline_td_regression_skips_player_without_gsis_id() -> None:
    play_values = _play_values([("gsis-a", "target", "1-5", 7.0, 1.0)])
    rows = [_row("a", "WR", 300.0, 1.0, gsis_id="")]
    _, flags = compute_yardline_td_regression(rows, play_values, {"gsis-a": "WR"}, min_yards=250)
    assert flags == []
