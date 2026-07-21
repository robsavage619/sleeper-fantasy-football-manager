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


# --- availability discount (the arena's validated lever, ported live) ----------------


def test_availability_factor_tiers() -> None:
    from sleeper_ffm.model.news_feed import availability_factor

    assert availability_factor(None) == 1.0
    assert availability_factor("Out") == 0.0
    assert availability_factor("IR") == 0.0
    assert availability_factor("Doubtful") == 0.0  # nearly-out, zeroed like the arena
    assert availability_factor("Questionable") == 0.8
    assert availability_factor("Probable") == 1.0  # unknown/benign → no discount


def test_apply_availability_fallback_source_gets_full_discount_and_warns() -> None:
    # nflverse_avg is injury-blind, so it gets the full Out->0 / Questionable->0.8 discount.
    projections = [
        ss.PlayerProjection("hurt", "Hurt Star", "RB", "BAL", 22.0, "HIGH", "nflverse_avg", "x"),
        ss.PlayerProjection("q", "Iffy Guy", "WR", "KC", 15.0, "HIGH", "nflverse_avg", "y"),
        ss.PlayerProjection("ok", "Healthy", "WR", "SF", 12.0, "HIGH", "nflverse_avg", "z"),
    ]
    dump = {
        "hurt": {"injury_status": "Out"},
        "q": {"injury_status": "Questionable"},
        "ok": {"injury_status": None},
    }
    warnings: list[str] = []
    ss._apply_availability(projections, dump, warnings)

    assert projections[0].projected_pts == 0.0  # Out zeroed
    assert projections[0].injury_status == "Out"
    assert projections[1].projected_pts == 12.0  # 15 * 0.8
    assert projections[2].projected_pts == 12.0  # untouched
    assert len(warnings) == 1 and "Hurt Star" in warnings[0] and "Iffy Guy" in warnings[0]


def test_apply_availability_trusts_the_provider_for_soft_designations() -> None:
    # Rotowire already prices injuries, so a provider Questionable is NOT re-discounted...
    projections = [
        ss.PlayerProjection("q", "Iffy Guy", "WR", "KC", 15.0, "HIGH", "provider", "y"),
        ss.PlayerProjection("out", "Ghost", "RB", "BAL", 6.5, "HIGH", "provider", "z"),
    ]
    dump = {"q": {"injury_status": "Questionable"}, "out": {"injury_status": "Out"}}
    warnings: list[str] = []
    ss._apply_availability(projections, dump, warnings)

    assert projections[0].projected_pts == 15.0  # provider Questionable left as-is
    assert projections[0].injury_status == "Questionable"  # status still recorded
    # ...but a hard-out is still zeroed even on the provider path (stale-feed safety net).
    assert projections[1].projected_pts == 0.0
    assert "Ghost" in warnings[0] and "Iffy Guy" not in warnings[0]


def test_apply_availability_no_warning_when_everyone_is_healthy() -> None:
    projections = [ss.PlayerProjection("a", "A", "RB", "BAL", 10.0, "HIGH", "provider", "")]
    warnings: list[str] = []
    ss._apply_availability(projections, {"a": {"injury_status": None}}, warnings)
    assert warnings == []
    assert projections[0].projected_pts == 10.0


def test_out_player_falls_out_of_the_optimal_lineup() -> None:
    """End-to-end intent: zeroing an Out star drops him below a healthy bench player."""
    projections = [
        ss.PlayerProjection("star", "Out Star", "RB", "BAL", 25.0, "HIGH", "provider", ""),
        ss.PlayerProjection("bench", "Healthy Backup", "RB", "SF", 9.0, "MED", "nflverse_avg", ""),
    ]
    ss._apply_availability(projections, {"star": {"injury_status": "IR"}}, [])
    # After the discount, the healthy backup outranks the zeroed star.
    assert projections[0].projected_pts == 0.0
    assert projections[1].projected_pts > projections[0].projected_pts
