"""Hermetic unit tests for player-sabermetric pure helpers (frozen, hand-computable)."""

from __future__ import annotations

import math

import polars as pl

from sleeper_ffm.model import sabermetrics as sm


def test_percentile_linear_interpolation() -> None:
    values = [0.0, 5.0, 10.0, 15.0, 20.0]
    assert sm._percentile(values, 50) == 10.0
    # rank = 0.2 * 4 = 0.8 -> 0 + 0.8*(5-0) = 4.0
    assert sm._percentile(values, 20) == 4.0
    # rank = 0.9 * 4 = 3.6 -> 15 + 0.6*(20-15) = 18.0
    assert sm._percentile(values, 90) == 18.0


def test_percentile_edge_cases() -> None:
    assert sm._percentile([], 50) == 0.0
    assert sm._percentile([7.0], 90) == 7.0


def test_rank_threshold_uses_1_indexed_rank() -> None:
    # sorted desc: [30, 20, 10, 5]; rank 2 -> index 1 -> 20
    assert sm.rank_threshold([10.0, 20.0, 5.0, 30.0], 2) == 20.0
    # rank deeper than the field -> lowest score present
    assert sm.rank_threshold([10.0, 20.0, 5.0, 30.0], 10) == 5.0
    assert sm.rank_threshold([], 1) == 0.0


def test_consistency_profile_boom_bust_hand_computed() -> None:
    weekly_fp = [2.0, 8.0, 12.0, 20.0, 25.0]
    out = sm.consistency_profile(weekly_fp, startable=18.0, replacement=6.0)
    assert out["games"] == 5
    # booms: 20, 25 -> 2/5 ; busts: 2 (<6) -> 1/5
    assert out["boom_pct"] == 0.4
    assert out["bust_pct"] == 0.2
    # floor p20: rank 0.8 -> 2 + 0.8*(8-2) = 6.8 ; median 12 ; ceiling p90: 20 + 0.6*5 = 23
    assert out["floor"] == 6.8
    assert out["median"] == 12.0
    assert out["ceiling"] == 23.0
    # CV: pstdev/mean, mean = 13.4, pstdev = sqrt(339.2/5)
    expected_cv = round(math.sqrt(339.2 / 5) / 13.4, 3)
    assert out["volatility"] == expected_cv


def test_consistency_profile_empty() -> None:
    out = sm.consistency_profile([], startable=10.0, replacement=5.0)
    assert out["games"] == 0
    assert out["boom_pct"] is None


def test_td_dependence() -> None:
    assert sm.td_dependence(12.0, 48.0) == 0.25
    assert sm.td_dependence(6.0, 0.0) is None


def test_opportunity_trend_last4_vs_prior() -> None:
    series = [1.0, 1.0, 1.0, 1.0, 5.0, 5.0, 5.0, 5.0]
    assert sm.opportunity_trend(series, window=4) == 4.0
    # not enough prior weeks
    assert sm.opportunity_trend([1.0, 2.0, 3.0, 4.0], window=4) is None


def test_age_curve_expected_ascent_and_decay() -> None:
    # WR 23 -> 24, still pre-peak (peak 27) -> ascent 1.06
    assert sm.age_curve_expected(100.0, 23.0, "WR") == round(100.0 * 1.06, 3)
    # RB 30 -> 31, well past peak (25) -> steep RB decay 0.82
    assert sm.age_curve_expected(100.0, 30.0, "RB") == round(100.0 * 0.82, 3)


def test_age_curve_residual_sign() -> None:
    assert sm.age_curve_residual(110.0, 106.0) == 4.0
    assert sm.age_curve_residual(90.0, 106.0) == -16.0


def test_expected_fp_linear_combo() -> None:
    opps = {"targets": 100.0, "carries": 50.0}
    coeffs = {"targets": 1.5, "carries": 0.6}
    # 100*1.5 + 50*0.6 = 180
    assert sm.expected_fp(opps, coeffs) == 180.0


_SCORING = {"rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0, "rush_yd": 0.1, "rush_td": 6.0}


def _pbp_row(
    receiver: str | None = None,
    rusher: str | None = None,
    yardline_100: float | None = 50.0,
    yards_gained: float = 5.0,
    touchdown: float = 0.0,
    complete_pass: float = 1.0,
) -> dict:
    return {
        "receiver_player_id": receiver,
        "rusher_player_id": rusher,
        "yardline_100": yardline_100,
        "yards_gained": yards_gained,
        "touchdown": touchdown,
        "complete_pass": complete_pass,
    }


def _pbp_frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "receiver_player_id": pl.Utf8,
            "rusher_player_id": pl.Utf8,
            "yardline_100": pl.Float64,
            "yards_gained": pl.Float64,
            "touchdown": pl.Float64,
            "complete_pass": pl.Float64,
        },
    )


def test_pbp_play_value_computes_target_and_carry_fp() -> None:
    pbp = _pbp_frame(
        [
            # Goal-line TD catch: 1 (rec) + 5*0.1 (yards) + 6 (td) = 7.5
            _pbp_row(receiver="A", yardline_100=5.0, yards_gained=5.0, touchdown=1.0),
            # Own-half rush, no TD: 8*0.1 = 0.8
            _pbp_row(rusher="B", yardline_100=60.0, yards_gained=8.0),
        ]
    )
    values = sm.pbp_play_value(pbp, _SCORING)
    target_row = values.filter(values["kind"] == "target").row(0, named=True)
    carry_row = values.filter(values["kind"] == "carry").row(0, named=True)
    assert target_row["player_id"] == "A"
    assert target_row["yardline_bin"] == "1-5"
    assert target_row["fp"] == 7.5
    assert target_row["touchdown"] == 1.0
    assert carry_row["player_id"] == "B"
    assert carry_row["yardline_bin"] == "41+"
    assert carry_row["fp"] == 0.8
    assert carry_row["touchdown"] == 0.0


def test_pbp_play_value_bins_the_whole_field() -> None:
    # One carry per bin, including the boundaries, plus a play with no yard line.
    pbp = _pbp_frame(
        [_pbp_row(rusher="A", yardline_100=y) for y in (1.0, 5.0, 6.0, 10.0, 11.0, 20.0, 21.0)]
        + [_pbp_row(rusher="A", yardline_100=40.0), _pbp_row(rusher="A", yardline_100=41.0)]
    )
    values = sm.pbp_play_value(pbp, _SCORING)
    assert values["yardline_bin"].to_list() == [
        "1-5",
        "1-5",
        "6-10",
        "6-10",
        "11-20",
        "11-20",
        "21-40",
        "21-40",
        "41+",
    ]


def test_pbp_play_value_null_yardline_gets_no_bin() -> None:
    # A play with no recorded yard line must not be priced as if it came from midfield.
    values = sm.pbp_play_value(_pbp_frame([_pbp_row(rusher="A", yardline_100=None)]), _SCORING)
    assert values["yardline_bin"].to_list() == [None]
    assert sm.player_yardline_opportunities(values, "A") == {
        key: 0.0 for _, _, key in sm.BUCKET_KEYS
    }


def test_pbp_play_value_missing_columns_returns_empty() -> None:
    empty = sm.pbp_play_value(pl.DataFrame({"foo": [1]}), _SCORING)
    assert empty.is_empty()
    assert set(empty.columns) == {"player_id", "kind", "yardline_bin", "fp", "touchdown"}


def test_yardline_usage_coefficients_splits_by_bucket() -> None:
    # WR "A": one goal-line TD target (7.5 fp) and one own-half incompletion (0 fp).
    pbp = _pbp_frame(
        [
            _pbp_row(receiver="A", yardline_100=5.0, yards_gained=5.0, touchdown=1.0),
            _pbp_row(receiver="A", yardline_100=60.0, yards_gained=0.0, complete_pass=0.0),
        ]
    )
    values = sm.pbp_play_value(pbp, _SCORING)
    coeffs = sm.yardline_usage_coefficients(values, {"A": "WR"})
    assert coeffs["WR"]["1-5_targets"] == 7.5
    assert coeffs["WR"]["41+_targets"] == 0.0
    # Bins with zero observed plays fall back to the flat defaults.
    assert coeffs["WR"]["11-20_targets"] == 1.7
    assert coeffs["RB"]["21-40_carries"] == 0.55


def test_yardline_td_rates_price_the_goal_line_above_the_red_zone_edge() -> None:
    # The gradient the old binary red-zone flag collapsed: both plays are "red zone",
    # but one converts and the other does not.
    pbp = _pbp_frame(
        [
            _pbp_row(rusher="A", yardline_100=2.0, yards_gained=2.0, touchdown=1.0),
            _pbp_row(rusher="B", yardline_100=18.0, yards_gained=3.0),
        ]
    )
    values = sm.pbp_play_value(pbp, _SCORING)
    rates = sm.yardline_td_rates(values, {"A": "RB", "B": "RB"})
    assert rates["RB"]["1-5_carries"] == 1.0
    assert rates["RB"]["11-20_carries"] == 0.0


def test_player_yardline_opportunities_counts_by_bucket() -> None:
    pbp = _pbp_frame(
        [
            _pbp_row(receiver="A", yardline_100=5.0, yards_gained=5.0, touchdown=1.0),
            _pbp_row(receiver="A", yardline_100=60.0, yards_gained=3.0),
            _pbp_row(rusher="A", yardline_100=2.0, yards_gained=2.0, touchdown=1.0),
        ]
    )
    values = sm.pbp_play_value(pbp, _SCORING)
    opps = sm.player_yardline_opportunities(values, "A")
    assert opps == {
        key: {"1-5_targets": 1.0, "41+_targets": 1.0, "1-5_carries": 1.0}.get(key, 0.0)
        for _, _, key in sm.BUCKET_KEYS
    }


def test_player_yardline_opportunities_unknown_player_is_zero() -> None:
    empty = pl.DataFrame(
        schema={"player_id": pl.Utf8, "kind": pl.Utf8, "yardline_bin": pl.Utf8, "fp": pl.Float64}
    )
    opps = sm.player_yardline_opportunities(empty, "nobody")
    assert opps == {key: 0.0 for _, _, key in sm.BUCKET_KEYS}
