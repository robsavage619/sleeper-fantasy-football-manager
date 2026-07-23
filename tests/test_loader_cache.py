from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from sleeper_ffm.nflverse import loader


def _write_weekly(path, season: int) -> None:
    pl.DataFrame({"season": [season], "season_type": ["REG"], "player_id": ["x"]}).write_parquet(
        path
    )


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


# ---- single-file datasets (schedules, rosters, snaps, seasonal) -------------
#
# These share one parquet rather than one per season. A naive "return the cache
# if it exists" check pins the file to whatever the first caller asked for, so
# every one of them must fetch and merge the seasons it is missing.


def _fake_fetch(seasons):
    """Stand-in for an nfl_data_py importer, returning one row per season."""
    import pandas as pd

    return pd.DataFrame({"season": list(seasons), "player_id": ["x"] * len(seasons)})


def _seasons_in(df: pl.DataFrame) -> list[int]:
    return sorted(df["season"].unique().to_list())


def _loader_case(name: str):
    return {
        "schedules": (loader.load_schedules, "schedules.parquet", "import_schedules"),
        "rosters": (loader.load_rosters, "rosters.parquet", "import_weekly_rosters"),
        "snaps": (loader.load_snaps, "snaps.parquet", "import_snap_counts"),
        "seasonal": (loader.load_seasonal, "seasonal.parquet", "import_seasonal_data"),
    }[name]


@pytest.mark.parametrize("name", ["schedules", "rosters", "snaps", "seasonal"])
def test_narrow_then_wide_request_fetches_missing_seasons(name, tmp_path, monkeypatch) -> None:
    load, filename, importer = _loader_case(name)
    monkeypatch.setattr(loader, "NFLVERSE_DIR", tmp_path)
    monkeypatch.setattr(loader.nfl, importer, _fake_fetch)

    # First caller pins the file to a single season...
    assert _seasons_in(load(seasons=[2022])) == [2022]

    # ...a later caller asking for more must still get all of them.
    df = load(seasons=[2022, 2023, 2024])
    assert _seasons_in(df) == [2022, 2023, 2024]
    assert _seasons_in(pl.read_parquet(tmp_path / filename)) == [2022, 2023, 2024]


@pytest.mark.parametrize("name", ["schedules", "rosters", "snaps", "seasonal"])
def test_cached_seasons_are_not_refetched(name, tmp_path, monkeypatch) -> None:
    load, _filename, importer = _loader_case(name)
    monkeypatch.setattr(loader, "NFLVERSE_DIR", tmp_path)
    monkeypatch.setattr(loader.nfl, importer, _fake_fetch)
    load(seasons=[2022, 2023])

    def _no_fetch(_seasons):
        raise AssertionError("fully cached request should not trigger a fetch")

    monkeypatch.setattr(loader.nfl, importer, _no_fetch)
    assert _seasons_in(load(seasons=[2022])) == [2022, 2023]


def test_seasonal_skips_seasons_past_legacy_coverage(tmp_path, monkeypatch) -> None:
    # nflverse stopped publishing player_stats_{year} after 2024; requesting 2025
    # is a hard 404, so it must be clamped out rather than passed to the fetch.
    monkeypatch.setattr(loader, "NFLVERSE_DIR", tmp_path)

    def _fetch_guarding_coverage(seasons):
        assert all(s <= loader._SEASONAL_LAST_SEASON for s in seasons), seasons
        return _fake_fetch(seasons)

    monkeypatch.setattr(loader.nfl, "import_seasonal_data", _fetch_guarding_coverage)

    df = loader.load_seasonal(seasons=[2023, 2024, 2025])
    assert _seasons_in(df) == [2023, 2024]


def test_seasonal_returns_empty_when_all_seasons_are_uncovered(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(loader, "NFLVERSE_DIR", tmp_path)

    def _no_fetch(_seasons):
        raise AssertionError("uncovered seasons should not trigger a fetch")

    monkeypatch.setattr(loader.nfl, "import_seasonal_data", _no_fetch)
    assert loader.load_seasonal(seasons=[2025, 2026]).is_empty()


# ---- cross-era schema concatenation ----------------------------------------


def test_concat_across_schemas_unions_differing_columns() -> None:
    a = pl.DataFrame({"season": [2023], "game_type": ["REG"]})
    b = pl.DataFrame({"season": [2024], "season_type": ["REG"]})
    out = loader._concat_across_schemas([a, b])
    assert sorted(out["season"].to_list()) == [2023, 2024]
    assert {"game_type", "season_type"} <= set(out.columns)


def test_concat_across_schemas_handles_empty_input() -> None:
    assert loader._concat_across_schemas([]).is_empty()


def test_depth_charts_merge_both_formats(tmp_path, monkeypatch) -> None:
    # The two eras have to come back as one frame: the newer timestamped feed is
    # normalised onto the weekly schema rather than dropped, so a season served in
    # the new format is not silently missing from depth history.
    monkeypatch.setattr(loader, "NFLVERSE_DIR", tmp_path)
    monkeypatch.setattr(
        loader,
        "_schedule_week_index",
        lambda: pl.DataFrame({"season": [2025], "week": [1], "_week_start": [date(2025, 9, 4)]}),
    )
    (tmp_path / "depth_charts").mkdir()
    pl.DataFrame({"season": [2024], "week": [1.0], "full_name": ["A Player"]}).write_parquet(
        tmp_path / "depth_charts" / "2024.parquet"
    )
    pl.DataFrame(
        {"dt": ["2025-09-10T07:32:09Z"], "player_name": ["B Player"], "team": ["ARI"]}
    ).write_parquet(tmp_path / "depth_charts" / "2025.parquet")
    loader.clear_stale_fallbacks()

    df = loader.load_depth_charts(seasons=[2024, 2025])
    assert sorted(df["season"].to_list()) == [2024, 2025]
    assert "nflverse_depth_charts" not in loader.stale_fallbacks()


# ---- depth-chart snapshot normalisation ------------------------------------


def _snapshot_frame() -> pl.DataFrame:
    """nflverse's newer timestamped depth-chart shape."""
    return pl.DataFrame(
        {
            # One capture inside week 1, one after week 2 kicks off.
            "dt": ["2025-09-08T07:00:00Z", "2025-09-12T07:00:00Z"],
            "team": ["ARI", "ARI"],
            "player_name": ["Trey McBride", "Trey McBride"],
            "pos_abb": ["TE", "TE"],
            "pos_rank": [1, 1],
            "gsis_id": ["00-0037741", "00-0037741"],
        }
    )


def _week_index() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2025, 2025],
            "week": [1, 2],
            "_week_start": [date(2025, 9, 4), date(2025, 9, 11)],
        }
    )


def test_snapshot_format_is_mapped_onto_the_weekly_schema(monkeypatch) -> None:
    monkeypatch.setattr(loader, "_schedule_week_index", lambda: _week_index())
    out = loader._normalize_depth_snapshot(_snapshot_frame())

    assert {"season", "week", "club_code", "full_name", "depth_position"} <= set(out.columns)
    # Each capture lands in the most recent week that had already kicked off.
    assert sorted(out["week"].to_list()) == [1, 2]
    assert out["club_code"].unique().to_list() == ["ARI"]
    # depth_team carried the position rank as a string in the legacy feed.
    assert out["depth_team"].dtype == pl.Utf8


def test_legacy_frames_pass_through_untouched() -> None:
    legacy = pl.DataFrame({"season": [2024], "week": [1.0], "full_name": ["A Player"]})
    assert loader._normalize_depth_snapshot(legacy).equals(legacy)


def test_unrecognised_shape_yields_empty_rather_than_garbage() -> None:
    assert loader._normalize_depth_snapshot(pl.DataFrame({"nonsense": [1]})).is_empty()


def test_snapshot_without_a_schedule_is_dropped_not_guessed(monkeypatch) -> None:
    # Inventing a week number would corrupt the ordering every consumer sorts on,
    # so an unavailable schedule must drop the frame instead.
    monkeypatch.setattr(loader, "_schedule_week_index", lambda: pl.DataFrame())
    assert loader._normalize_depth_snapshot(_snapshot_frame()).is_empty()
