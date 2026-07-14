"""Hermetic unit tests for player-sabermetric pure helpers (frozen, hand-computable)."""

from __future__ import annotations

import math

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
