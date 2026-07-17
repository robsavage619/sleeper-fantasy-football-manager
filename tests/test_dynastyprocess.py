"""Tests for the DynastyProcess fallback market source (file I/O only, no network).

``fetch()`` is the sole fallback when FantasyCalc fails (see ``market/blend.py``
``market_anchor``), so it needs the same "never actually hit the network in tests"
treatment as the price-history store (see ``test_price_history.py``): the on-disk
cache path is redirected to ``tmp_path`` and the network fetch itself is stubbed.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from sleeper_ffm.market import dynastyprocess as dp


def _with_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dp, "_CACHE_DIR", tmp_path)


# ---------------------------------------------------------------------------
# _is_stale
# ---------------------------------------------------------------------------


def test_is_stale_missing_file_is_stale(tmp_path: Path) -> None:
    assert dp._is_stale(tmp_path / "missing.csv") is True


def test_is_stale_fresh_file_is_not_stale(tmp_path: Path) -> None:
    path = tmp_path / "fresh.csv"
    path.write_text("sleeper_id,value\n")
    assert dp._is_stale(path) is False


def test_is_stale_old_file_is_stale(tmp_path: Path) -> None:
    path = tmp_path / "old.csv"
    path.write_text("sleeper_id,value\n")
    old_time = time.time() - dp._CACHE_TTL_SECONDS - 1
    import os

    os.utime(path, (old_time, old_time))
    assert dp._is_stale(path) is True


# ---------------------------------------------------------------------------
# _load_csv_text — cache hit vs stale-refetch
# ---------------------------------------------------------------------------


def test_load_csv_text_cache_hit_skips_fetch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_cache_dir(monkeypatch, tmp_path)
    cached = dp._cache_path()
    cached.write_text("sleeper_id,value\n100,5000\n")

    def _boom() -> str:
        raise AssertionError("should not fetch when cache is fresh")

    monkeypatch.setattr(dp, "_fetch_fresh", _boom)

    text = dp._load_csv_text()
    assert "100,5000" in text


def test_load_csv_text_stale_cache_refetches_and_rewrites(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _with_cache_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(dp, "_fetch_fresh", lambda: "sleeper_id,value\n200,4000\n")

    text = dp._load_csv_text()
    assert "200,4000" in text
    assert dp._cache_path().read_text() == "sleeper_id,value\n200,4000\n"


# ---------------------------------------------------------------------------
# fetch() — CSV parsing and graceful degradation
# ---------------------------------------------------------------------------


def test_fetch_parses_valid_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    csv_text = (
        "sleeper_id,value,player_name\n"
        "100,5000,Player A\n"
        "200,3200.5,Player B\n"
    )
    monkeypatch.setattr(dp, "_load_csv_text", lambda: csv_text)

    result = dp.fetch()

    assert result == {"100": 5000.0, "200": 3200.5}


def test_fetch_skips_rows_missing_sleeper_id_or_value(monkeypatch: pytest.MonkeyPatch) -> None:
    csv_text = (
        "sleeper_id,value\n"
        ",5000\n"  # no sleeper_id
        "300,\n"  # no value
        "400,4100\n"  # valid
    )
    monkeypatch.setattr(dp, "_load_csv_text", lambda: csv_text)

    result = dp.fetch()

    assert result == {"400": 4100.0}


def test_fetch_skips_non_numeric_value(monkeypatch: pytest.MonkeyPatch) -> None:
    csv_text = "sleeper_id,value\n500,not-a-number\n600,1000\n"
    monkeypatch.setattr(dp, "_load_csv_text", lambda: csv_text)

    result = dp.fetch()

    assert result == {"600": 1000.0}


def test_fetch_returns_empty_dict_on_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> str:
        raise OSError("network unavailable")

    monkeypatch.setattr(dp, "_load_csv_text", _boom)

    assert dp.fetch() == {}


def test_fetch_empty_csv_returns_empty_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dp, "_load_csv_text", lambda: "sleeper_id,value\n")
    assert dp.fetch() == {}
