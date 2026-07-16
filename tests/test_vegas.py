"""Tests for the Vegas game-environment layer (pure helpers — no network)."""

from __future__ import annotations

from sleeper_ffm.model.vegas import blowout_risk, implied_totals


def test_implied_totals_favorite_and_underdog() -> None:
    # KC (home) favored by 3 in a 46-point game -> 24.5/21.5, matches the verified
    # sign convention (positive spread_line = home favored).
    home, away = implied_totals(spread_line=3.0, total_line=46.0)
    assert home == 24.5
    assert away == 21.5


def test_implied_totals_road_favorite() -> None:
    # Negative spread_line = away team favored.
    home, away = implied_totals(spread_line=-3.0, total_line=49.0)
    assert home == 23.0
    assert away == 26.0


def test_implied_totals_pick_em() -> None:
    home, away = implied_totals(spread_line=0.0, total_line=44.0)
    assert home == away == 22.0


def test_blowout_risk_scales_with_total() -> None:
    # Same 14-point spread reads riskier in a low-scoring game than a shootout.
    low_total_risk = blowout_risk(team_spread=14.0, game_total=33.0)
    high_total_risk = blowout_risk(team_spread=14.0, game_total=55.0)
    assert low_total_risk is not None and high_total_risk is not None
    assert low_total_risk > high_total_risk


def test_blowout_risk_clips_to_one() -> None:
    assert blowout_risk(team_spread=30.0, game_total=30.0) == 1.0


def test_blowout_risk_missing_inputs() -> None:
    assert blowout_risk(None, 44.0) is None
    assert blowout_risk(3.0, None) is None
    assert blowout_risk(3.0, 0.0) is None
