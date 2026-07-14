"""Tests for the contention-window classifier (pure logic — no network)."""

from __future__ import annotations

from sleeper_ffm.model.contention import _core_profile, classify_window


def test_win_now_is_good_odds_old_core() -> None:
    label, _seeking, shedding, _ = classify_window(0.15, 0.70, core_age=28.5, young_share=0.2)
    assert label == "WIN-NOW"
    assert "picks" in shedding


def test_sustain_is_good_odds_young_core() -> None:
    label, *_ = classify_window(0.25, 0.70, core_age=24.0, young_share=0.7)
    assert label == "SUSTAIN"


def test_rebuild_is_bad_odds_old_core() -> None:
    label, *_ = classify_window(0.0, 0.10, core_age=29.0, young_share=0.1)
    assert label == "REBUILD"


def test_retool_is_bad_odds_young_core() -> None:
    label, *_ = classify_window(0.02, 0.20, core_age=23.5, young_share=0.8)
    assert label == "RETOOL"


def test_hold_is_the_muddled_middle() -> None:
    label, *_ = classify_window(0.08, 0.45, core_age=27.0, young_share=0.4)
    assert label == "HOLD"


def test_core_profile_weights_by_value_and_flags_youth() -> None:
    # High-value old star dominates the weighted age; young share is value-weighted too.
    vals = [(1000.0, 30.0), (100.0, 22.0), (100.0, 23.0)]
    age, young_share = _core_profile(vals)
    assert age > 28.0  # dominated by the 1000-value 30-year-old
    assert 0.16 < young_share < 0.18  # 200 / 1200


def test_core_profile_empty() -> None:
    assert _core_profile([]) == (0.0, 0.0)
