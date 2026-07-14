"""Tests for the gameday win-probability core (pure — no network)."""

from __future__ import annotations

from sleeper_ffm.model.gameday import win_probability


def test_even_teams_are_coinflip() -> None:
    assert win_probability(100.0, 100.0, 20.0, 20.0) == 0.5


def test_stronger_team_favored() -> None:
    wp = win_probability(120.0, 100.0, 20.0, 20.0)
    assert 0.5 < wp < 1.0


def test_weaker_team_underdog() -> None:
    assert win_probability(90.0, 110.0, 20.0, 20.0) < 0.5


def test_probabilities_are_complementary() -> None:
    a = win_probability(115.0, 100.0, 18.0, 22.0)
    b = win_probability(100.0, 115.0, 22.0, 18.0)
    assert abs((a + b) - 1.0) < 1e-6


def test_zero_variance_is_step_function() -> None:
    assert win_probability(110.0, 100.0, 0.0, 0.0) == 1.0
    assert win_probability(100.0, 110.0, 0.0, 0.0) == 0.0
    assert win_probability(100.0, 100.0, 0.0, 0.0) == 0.5
