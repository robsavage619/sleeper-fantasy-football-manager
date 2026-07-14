from __future__ import annotations

import polars as pl

from sleeper_ffm.nflverse import loader


def _write_weekly(path, season: int) -> None:
    pl.DataFrame(
        {"season": [season], "season_type": ["REG"], "player_id": ["x"]}
    ).write_parquet(path)


def test_completed_season_is_cache_hit(tmp_path, monkeypatch) -> None:
    season = loader._CURRENT_SEASON
    _write_weekly(tmp_path / f"{season}.parquet", season)
    monkeypatch.setattr(loader, "_weekly_path", lambda s: tmp_path / f"{s}.parquet")

    def _no_fetch(_year: int):
        raise AssertionError("completed-season cache should not trigger a fetch")

    monkeypatch.setattr(loader, "_fetch_weekly_season", _no_fetch)

    df = loader.load_weekly(seasons=[season])
    assert not df.is_empty()


def test_fetch_failure_falls_back_to_cache(tmp_path, monkeypatch) -> None:
    # A future season is always in the fetch list; when the fetch fails but a
    # cached parquet exists, load_weekly must fall back to it, not drop it.
    season = loader._CURRENT_SEASON + 1
    _write_weekly(tmp_path / f"{season}.parquet", season)
    monkeypatch.setattr(loader, "_weekly_path", lambda s: tmp_path / f"{s}.parquet")
    monkeypatch.setattr(loader, "_fetch_weekly_season", lambda _y: None)

    df = loader.load_weekly(seasons=[season])
    assert not df.is_empty()
