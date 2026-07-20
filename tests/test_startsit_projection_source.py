from __future__ import annotations

import pytest

from sleeper_ffm.season import startsit as ss

_PLAYERS = {"p1": {"full_name": "Test Back", "position": "RB", "team": "BAL"}}
_WEEKLY = {"p1": {"games_played": 8, "season_avg": 10.0, "last4_avg": 12.0, "last4_games": 4}}


@pytest.fixture(autouse=True)
def _neutral_vegas(monkeypatch) -> None:
    """Pin the Vegas multiplier so source behaviour is what's under test."""
    monkeypatch.setattr(ss, "environment_multiplier", lambda *a, **k: 1.20)


def _project(estimates: dict[str, ss._WeekEstimate] | None) -> ss.PlayerProjection:
    return ss._project_player("p1", _PLAYERS, _WEEKLY, {}, 2025, 6, estimates)


def test_provider_estimate_wins_over_the_nflverse_average() -> None:
    out = _project({"p1": ss._WeekEstimate(points=17.5, floor=8.0, ceiling=28.0)})
    assert out.source == "provider"
    assert out.projected_pts == 17.5
    assert out.confidence == "HIGH"


def test_provider_points_are_not_scaled_by_vegas() -> None:
    """The provider's weekly number already prices the matchup — scaling double-counts."""
    out = _project({"p1": ss._WeekEstimate(points=17.5)})
    assert out.projected_pts == 17.5  # not 17.5 * 1.20


def test_fallback_path_still_applies_the_vegas_multiplier() -> None:
    out = _project(None)
    assert out.source == "nflverse_avg"
    assert out.projected_pts == pytest.approx(14.4)  # 12.0 last-4 * 1.20


def test_missing_provider_entry_falls_through_to_the_average() -> None:
    """An empty estimate (shape only, no points) must not be read as a 0.0 projection."""
    out = _project({"p1": ss._WeekEstimate(points=None, floor=5.0, ceiling=19.0)})
    assert out.source == "nflverse_avg"
    assert out.projected_pts == pytest.approx(14.4)


def test_simulated_spread_is_carried_on_the_fallback_path_too() -> None:
    out = _project({"p1": ss._WeekEstimate(points=None, floor=5.0, ceiling=19.0)})
    assert (out.floor, out.ceiling) == (5.0, 19.0)
    assert "sim floor 5.0/ceil 19.0" in out.notes


def test_absent_distribution_leaves_the_spread_at_zero() -> None:
    out = _project(None)
    assert (out.floor, out.ceiling) == (0.0, 0.0)
    assert "sim floor" not in out.notes


def test_unknown_player_still_gets_the_default_projection() -> None:
    out = ss._project_player("ghost", _PLAYERS, {}, {}, 2025, 6, None)
    assert out.source == "default"
    assert out.projected_pts == pytest.approx(6.0)  # 5.0 * 1.20
