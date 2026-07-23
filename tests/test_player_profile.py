from __future__ import annotations

import polars as pl

from sleeper_ffm.model.player_profile import (
    _fantasy_summary,
    _filter_snap_rows,
    _season_summaries,
    _weekly_rows,
)


def test_player_profile_aggregates_scored_weekly_rows() -> None:
    weekly = pl.DataFrame(
        [
            {
                "season": 2024,
                "week": 1,
                "recent_team": "LAC",
                "opponent_team": "LV",
                "fp_sffm": 21.5,
                "targets": 7,
                "carries": 1,
                "receptions": 5,
                "passing_yards": 0.0,
                "rushing_yards": 3.0,
                "receiving_yards": 80.0,
                "passing_tds": 0,
                "rushing_tds": 0,
                "receiving_tds": 1,
                "target_share": 0.24,
                "air_yards_share": 0.31,
            },
            {
                "season": 2024,
                "week": 2,
                "recent_team": "LAC",
                "opponent_team": "CAR",
                "fp_sffm": 4.2,
                "targets": 3,
                "carries": 0,
                "receptions": 1,
                "passing_yards": 0.0,
                "rushing_yards": 0.0,
                "receiving_yards": 22.0,
                "passing_tds": 0,
                "rushing_tds": 0,
                "receiving_tds": 0,
                "target_share": 0.11,
                "air_yards_share": 0.18,
            },
        ]
    )

    rows = _weekly_rows(weekly)
    seasons = _season_summaries(weekly)
    summary = _fantasy_summary(rows, seasons)

    assert rows[0]["touchdowns"] == 1
    assert seasons[0]["fantasy_points"] == 25.7
    assert seasons[0]["target_share"] == 17.5
    assert summary["boom_weeks"] == 1
    assert summary["bust_weeks"] == 1


def _snaps() -> pl.DataFrame:
    # One row per season, offense_pct rising over time — a veteran whose early
    # career looks nothing like the window the profile actually asked for.
    return pl.DataFrame(
        [
            {"player": "Vet Back", "team": "LAC", "season": season, "week": 1, "offense_pct": pct}
            for season, pct in [
                (2019, 0.10),
                (2020, 0.20),
                (2023, 0.80),
                (2024, 0.90),
                (2025, 1.00),
            ]
        ]
    )


def test_filter_snap_rows_limits_to_requested_seasons() -> None:
    identity = {"name": "Vet Back", "team": "LAC"}
    rows = _filter_snap_rows(_snaps(), identity, [2023, 2024, 2025])
    assert sorted(rows["season"].to_list()) == [2023, 2024, 2025]
    # Career average would be 60%; the requested window averages 90%.
    assert round(rows["offense_pct"].mean() * 100, 1) == 90.0


def test_filter_snap_rows_without_seasons_keeps_every_row() -> None:
    identity = {"name": "Vet Back", "team": "LAC"}
    assert len(_filter_snap_rows(_snaps(), identity, [])) == 5
