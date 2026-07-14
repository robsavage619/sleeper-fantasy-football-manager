"""Tests for the market data module (blend layer only — no network calls)."""

from __future__ import annotations

from unittest.mock import patch

from sleeper_ffm.market.blend import divergence
from sleeper_ffm.model.draft_class import class_strength_for_season


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


def test_class_strength_returns_one_when_no_market_price() -> None:
    with patch("sleeper_ffm.market.blend.market_pick_value", return_value=None):
        assert class_strength_for_season("2026") == 1.0


def test_class_strength_above_one_when_price_above_neutral_base() -> None:
    # CURRENT_LEAGUE_YEAR (no time discount) round bases are {1: 190, 2: 100, ...};
    # pricing both well above their neutral base should read as a loaded class.
    def fake_market_pick_value(season: str, round_: int) -> float | None:
        return {1: 380.0, 2: 200.0}.get(round_)  # 2x each round's neutral base

    with patch(
        "sleeper_ffm.market.blend.market_pick_value", side_effect=fake_market_pick_value
    ):
        strength = class_strength_for_season("2026")
    assert strength > 1.0


def test_class_strength_below_one_when_price_below_neutral_base() -> None:
    def fake_market_pick_value(season: str, round_: int) -> float | None:
        return {1: 95.0, 2: 50.0}.get(round_)  # 0.5x each round's neutral base

    with patch(
        "sleeper_ffm.market.blend.market_pick_value", side_effect=fake_market_pick_value
    ):
        strength = class_strength_for_season("2026")
    assert strength < 1.0


def test_class_strength_ignores_other_seasons() -> None:
    def fake_market_pick_value(season: str, round_: int) -> float | None:
        return 900.0 if season == "2027" else None

    with patch(
        "sleeper_ffm.market.blend.market_pick_value", side_effect=fake_market_pick_value
    ):
        assert class_strength_for_season("2026") == 1.0
