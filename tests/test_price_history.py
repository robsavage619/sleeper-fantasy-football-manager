"""Tests for the FantasyCalc price-history store (file I/O only, no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sleeper_ffm.market import price_history as ph


def _archive(tmp_path: Path, day: str, rows: list[dict]) -> None:
    (tmp_path / f"fantasycalc_{day}.json").write_text(json.dumps(rows))


def _entry(sleeper_id: str, value: float, name: str = "Test Player") -> dict:
    return {
        "player": {"sleeperId": sleeper_id, "name": name, "position": "WR", "maybeTeam": "KC"},
        "value": value,
    }


def _with_market_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ph, "_MARKET_DIR", tmp_path)


def test_load_price_history_empty_when_no_archives(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_market_dir(monkeypatch, tmp_path)
    index = ph.load_price_history()
    assert index.series == {}
    assert index.snapshot_dates == []


def test_load_price_history_orders_snapshots_oldest_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_market_dir(monkeypatch, tmp_path)
    _archive(tmp_path, "20260201", [_entry("100", 5000)])
    _archive(tmp_path, "20260101", [_entry("100", 4000)])
    index = ph.load_price_history()
    assert index.snapshot_dates == ["2026-01-01", "2026-02-01"]
    assert [p.value for p in index.series["100"]] == [4000, 5000]
    assert index.meta["100"].name == "Test Player"


def test_player_price_trend_no_history() -> None:
    trend = ph.player_price_trend("999", ph.PriceHistoryIndex(series={}, meta={}))
    assert trend.momentum_pct is None
    assert trend.zscore is None
    assert "No price history" in trend.note


def test_player_price_trend_single_snapshot() -> None:
    index = ph.PriceHistoryIndex(series={"1": [ph.PricePoint("2026-01-01", 5000)]}, meta={})
    trend = ph.player_price_trend("1", index)
    assert trend.momentum_pct is None
    assert "one snapshot" in trend.note.lower()


def test_player_price_trend_momentum_with_two_points() -> None:
    points = [ph.PricePoint("2026-01-01", 4000), ph.PricePoint("2026-02-01", 5000)]
    index = ph.PriceHistoryIndex(series={"1": points}, meta={})
    trend = ph.player_price_trend("1", index)
    assert trend.momentum_pct == 25.0
    assert trend.zscore is None  # below _MIN_SNAPSHOTS_FOR_SIGNAL


def test_player_price_trend_zscore_with_enough_history() -> None:
    values = [4000, 4100, 4050, 4900]  # jump on the latest snapshot
    points = [ph.PricePoint(f"2026-0{i + 1}-01", v) for i, v in enumerate(values)]
    index = ph.PriceHistoryIndex(series={"1": points}, meta={})
    trend = ph.player_price_trend("1", index)
    assert trend.momentum_pct == round((4900 - 4000) / 4000 * 100, 2)
    assert trend.zscore is not None and trend.zscore > 0  # latest is above trailing mean


def test_top_movers_filters_direction_and_sorts() -> None:
    index = ph.PriceHistoryIndex(
        series={
            "riser": [ph.PricePoint("2026-01-01", 4000), ph.PricePoint("2026-02-01", 6000)],
            "faller": [ph.PricePoint("2026-01-01", 4000), ph.PricePoint("2026-02-01", 2000)],
            "flat": [ph.PricePoint("2026-01-01", 4000), ph.PricePoint("2026-02-01", 4000)],
        },
        meta={},
    )
    risers = ph.top_movers(direction="up", index=index)
    fallers = ph.top_movers(direction="down", index=index)
    assert [t.sleeper_id for t in risers] == ["riser"]
    assert [t.sleeper_id for t in fallers] == ["faller"]


def test_top_movers_respects_min_snapshots() -> None:
    index = ph.PriceHistoryIndex(series={"only_one": [ph.PricePoint("2026-01-01", 4000)]}, meta={})
    assert ph.top_movers(direction="up", index=index) == []
