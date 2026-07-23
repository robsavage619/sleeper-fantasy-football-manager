"""NGS and PFR advanced loader tests (no network — fetches are monkeypatched)."""

from __future__ import annotations

import polars as pl
import pytest

from sleeper_ffm.nflverse import loader


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader, "NFLVERSE_DIR", tmp_path)
    loader.clear_stale_fallbacks()


def _frame(season: int) -> pl.DataFrame:
    return pl.DataFrame({"season": [season], "week": [1], "player_gsis_id": ["00-0000001"]})


def test_ngs_rejects_unknown_stat_type() -> None:
    with pytest.raises(ValueError, match="stat_type must be one of"):
        loader.load_ngs("kicking")


def test_pfr_rejects_unknown_stat_type() -> None:
    with pytest.raises(ValueError, match="stat_type must be one of"):
        loader.load_pfr_advanced("special_teams")


def test_ngs_skips_seasons_before_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    """NGS starts in 2016; earlier seasons must be dropped, not fetched and cached empty."""
    fetched: list[int] = []

    def _fake(stat_type: str, years: list[int]):
        fetched.extend(years)
        return _frame(years[0]).to_pandas()

    monkeypatch.setattr(loader.nfl, "import_ngs_data", _fake)
    loader.load_ngs("receiving", seasons=[2014, 2015, 2016])
    assert fetched == [2016]


def test_pfr_skips_seasons_before_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    fetched: list[int] = []

    def _fake(s_type: str, years: list[int]):
        fetched.extend(years)
        return _frame(years[0]).to_pandas()

    monkeypatch.setattr(loader.nfl, "import_weekly_pfr", _fake)
    loader.load_pfr_advanced("rec", seasons=[2016, 2017, 2018])
    assert fetched == [2018]


def test_ngs_completed_season_is_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    season = loader._CURRENT_SEASON
    dest = loader.NFLVERSE_DIR / "ngs" / "receiving" / f"{season}.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    _frame(season).write_parquet(dest)

    def _no_fetch(*_args, **_kwargs):
        raise AssertionError("cached completed season should not trigger a fetch")

    monkeypatch.setattr(loader.nfl, "import_ngs_data", _no_fetch)
    df = loader.load_ngs("receiving", seasons=[season])
    assert df.height == 1


def test_ngs_fetch_failure_falls_back_to_cache_and_records_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed refresh must serve the cache loudly, never silently."""
    season = loader._CURRENT_SEASON
    dest = loader.NFLVERSE_DIR / "ngs" / "rushing" / f"{season}.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    _frame(season).write_parquet(dest)

    def _boom(*_args, **_kwargs):
        raise OSError("nflverse unreachable")

    monkeypatch.setattr(loader.nfl, "import_ngs_data", _boom)
    df = loader.load_ngs("rushing", seasons=[season], force=True)

    assert df.height == 1
    assert "nflverse_ngs_rushing" in loader.stale_fallbacks()


def test_ngs_fetch_failure_without_cache_records_stale_and_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args, **_kwargs):
        raise OSError("nflverse unreachable")

    monkeypatch.setattr(loader.nfl, "import_ngs_data", _boom)
    df = loader.load_ngs("passing", seasons=[loader._CURRENT_SEASON])

    assert df.is_empty()
    assert "nflverse_ngs_passing" in loader.stale_fallbacks()


def test_ngs_successful_refresh_clears_stale_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    season = loader._CURRENT_SEASON
    loader._record_stale("nflverse_ngs_receiving", "earlier failure")
    monkeypatch.setattr(
        loader.nfl, "import_ngs_data", lambda _s, years: _frame(years[0]).to_pandas()
    )

    loader.load_ngs("receiving", seasons=[season])
    assert "nflverse_ngs_receiving" not in loader.stale_fallbacks()
