"""Tests for the market data module (blend layer only — no network calls)."""

from __future__ import annotations
from unittest.mock import patch

from sleeper_ffm.market.blend import class_strength_for_season, divergence


def test_divergence_positive_when_model_above_market() -> None:
    anchor = {"p1": 1000.0, "p2": 500.0}
    model = {"p1": 1200.0, "p2": 500.0}
    result = divergence(anchor, model)
    assert result["p1"] == 20.0
    assert result["p2"] == 0.0


def test_divergence_negative_when_model_below_market() -> None:
    anchor = {"p1": 1000.0}
    model = {"p1": 800.0}
    result = divergence(anchor, model)
    assert result["p1"] == -20.0


def test_divergence_excludes_players_not_in_both() -> None:
    anchor = {"p1": 500.0}
    model = {"p2": 400.0}
    result = divergence(anchor, model)
    assert result == {}


def test_divergence_skips_zero_market_value() -> None:
    anchor = {"p1": 0.0, "p2": 100.0}
    model = {"p1": 50.0, "p2": 100.0}
    result = divergence(anchor, model)
    assert "p1" not in result
    assert "p2" in result


def test_class_strength_returns_one_when_no_picks() -> None:
    with patch("sleeper_ffm.market.fantasycalc.fetch_picks", return_value={}):
        assert class_strength_for_season("2026") == 1.0


def test_class_strength_above_one_when_picks_above_historical() -> None:
    # FC pick values 2x the historical baseline → multiplier ≈ 2.0 (clamped)
    mock_picks = {
        ("2026", 1): 13_000.0,  # 2× historical 6500
        ("2026", 2): 7_000.0,   # 2× historical 3500
    }
    with patch("sleeper_ffm.market.fantasycalc.fetch_picks", return_value=mock_picks):
        strength = class_strength_for_season("2026")
    assert strength > 1.0


def test_class_strength_below_one_when_picks_below_historical() -> None:
    mock_picks = {
        ("2026", 1): 3_250.0,  # 0.5× historical 6500
        ("2026", 2): 1_750.0,  # 0.5× historical 3500
    }
    with patch("sleeper_ffm.market.fantasycalc.fetch_picks", return_value=mock_picks):
        strength = class_strength_for_season("2026")
    assert strength < 1.0


def test_class_strength_ignores_other_seasons() -> None:
    mock_picks = {("2027", 1): 9_000.0}
    with patch("sleeper_ffm.market.fantasycalc.fetch_picks", return_value=mock_picks):
        assert class_strength_for_season("2026") == 1.0
