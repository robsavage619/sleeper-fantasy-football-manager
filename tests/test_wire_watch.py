"""Tests for the wire early-warning helpers (pure logic — no network)."""

from __future__ import annotations

from sleeper_ffm.model.wire_watch import is_riser, snap_trend


def test_snap_trend_splits_recent_from_prior() -> None:
    weeks = [(1, 0.2), (2, 0.25), (3, 0.3), (4, 0.6), (5, 0.65), (6, 0.7)]
    trend = snap_trend(weeks, recent_n=3)
    assert trend is not None
    recent, prior, delta = trend
    assert recent == round((0.6 + 0.65 + 0.7) / 3, 3)
    assert prior == round((0.2 + 0.25 + 0.3) / 3, 3)
    assert delta == round(recent - prior, 3)


def test_snap_trend_none_when_too_few_weeks() -> None:
    assert snap_trend([(1, 0.5), (2, 0.6)], recent_n=3) is None


def test_snap_trend_ignores_week_order() -> None:
    a = snap_trend([(6, 0.7), (1, 0.2), (3, 0.3), (2, 0.25), (5, 0.65), (4, 0.6)])
    b = snap_trend([(1, 0.2), (2, 0.25), (3, 0.3), (4, 0.6), (5, 0.65), (6, 0.7)])
    assert a == b


def test_is_riser_requires_both_role_size_and_jump() -> None:
    assert is_riser(recent_pct=0.65, delta=0.35) is True
    assert is_riser(recent_pct=0.20, delta=0.35) is False  # big jump but still a small role
    assert is_riser(recent_pct=0.65, delta=0.05) is False  # big role but no change
