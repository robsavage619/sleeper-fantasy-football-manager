"""Tests for stadium/weather environment splits (pure helpers — no network)."""

from __future__ import annotations

from sleeper_ffm.model.stadium_weather import classify_env, summarize_player


def test_classify_controlled_ignores_weather() -> None:
    assert classify_env("dome", 10.0, 30.0) == {"controlled"}
    assert classify_env("closed", None, None) == {"controlled"}


def test_classify_exposed_cold_and_windy() -> None:
    assert classify_env("outdoors", 32.0, 20.0) == {"exposed", "cold", "windy"}
    assert classify_env("outdoors", 70.0, 5.0) == {"exposed"}
    assert classify_env("open", 38.0, 8.0) == {"exposed", "cold"}


def test_classify_missing_readings_stay_exposed_only() -> None:
    assert classify_env("outdoors", None, None) == {"exposed"}


def test_summarize_computes_bucket_deltas() -> None:
    games = [{"fp": 20.0, "roof": "dome", "temp": None, "wind": None, "stadium": "Dome A"}] * 3 + [
        {"fp": 8.0, "roof": "outdoors", "temp": 30.0, "wind": 20.0, "stadium": "Cold B"}
    ] * 3
    prof = summarize_player("p1", "Player One", "WR", games)
    assert prof.total_games == 6
    assert prof.overall_avg_fp == 14.0
    assert prof.splits["controlled"].delta == 6.0
    assert prof.splits["cold"].delta == -6.0
    assert prof.splits["windy"].delta == -6.0
    # Cold underperformance should raise a flag.
    assert any("cold" in f for f in prof.flags)


def test_summarize_drops_thin_buckets() -> None:
    games = [{"fp": 10.0, "roof": "outdoors", "temp": 32.0, "wind": 5.0, "stadium": "Y"}] * 2
    prof = summarize_player("p2", "Player Two", "RB", games)
    # Only 2 games — below _MIN_BUCKET_GAMES, so no split survives.
    assert prof.splits == {}
    assert prof.stadiums == []


def test_summarize_stadium_split_surfaces_with_enough_games() -> None:
    games = [
        {"fp": 25.0, "roof": "outdoors", "temp": 60.0, "wind": 5.0, "stadium": "Lucky Dome"}
    ] * 4
    prof = summarize_player("p3", "Player Three", "TE", games)
    assert prof.stadiums
    assert prof.stadiums[0].stadium == "Lucky Dome"
    assert prof.stadiums[0].games == 4
