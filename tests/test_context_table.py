"""Player-season context table tests (synthetic frames — no network, no disk reads)."""

from __future__ import annotations

import polars as pl
import pytest

import sleeper_ffm.model.context_table as ct


def _schedules() -> pl.DataFrame:
    """Two teams over two seasons; AAA keeps its staff, BBB replaces both coach and QB."""
    rows = []
    for season, bbb_coach, bbb_qb in ((2023, "Old Coach", "QB-B1"), (2024, "New Coach", "QB-B2")):
        for _week in (1, 2, 3):
            rows.append(
                {
                    "season": season,
                    "game_type": "REG",
                    "home_team": "AAA",
                    "away_team": "BBB",
                    "home_coach": "Steady Hand",
                    "away_coach": bbb_coach,
                    "home_qb_id": "QB-A1",
                    "away_qb_id": bbb_qb,
                }
            )
    # A playoff game with a different coach must be ignored by the REG filter.
    rows.append(
        {
            "season": 2024,
            "game_type": "DIV",
            "home_team": "AAA",
            "away_team": "BBB",
            "home_coach": "Interim Guy",
            "away_coach": "Interim Guy",
            "home_qb_id": "QB-A9",
            "away_qb_id": "QB-B9",
        }
    )
    return pl.DataFrame(rows)


def _weekly() -> pl.DataFrame:
    """Three players: one stays put, one switches teams, one departs the league."""
    rows = []

    def add(pid: str, name: str, pos: str, season: int, team: str, weeks: int, tgts: int) -> None:
        for week in range(1, weeks + 1):
            rows.append(
                {
                    "player_id": pid,
                    "player_display_name": name,
                    "position": pos,
                    "recent_team": team,
                    "season": season,
                    "week": week,
                    "season_type": "REG",
                    "targets": tgts,
                    "carries": 0,
                    "receptions": tgts,
                    "target_share": 0.25,
                    "air_yards_share": 0.30,
                    "wopr": 0.55,
                }
            )

    # Stays on AAA both years.
    add("P-STAY", "Stay Put", "WR", 2023, "AAA", 3, 10)
    add("P-STAY", "Stay Put", "WR", 2024, "AAA", 3, 10)
    # Leaves AAA for BBB — takes his prior volume with him.
    add("P-MOVE", "Move Along", "WR", 2023, "AAA", 3, 10)
    add("P-MOVE", "Move Along", "WR", 2024, "BBB", 3, 10)
    # On AAA in 2023 only, so his volume is vacated for 2024.
    add("P-GONE", "Gone Fishing", "WR", 2023, "AAA", 3, 20)
    return pl.DataFrame(rows)


@pytest.fixture(autouse=True)
def _stub_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ct, "load_schedules", lambda seasons=None: _schedules())
    monkeypatch.setattr(ct, "load_weekly", lambda seasons=None: _weekly())
    monkeypatch.setattr(ct, "_player_bio", lambda: pl.DataFrame({"gsis_id": [], "birthdate": []}))


def test_team_seasons_use_regular_season_only() -> None:
    ts = ct.build_team_seasons()
    aaa_2024 = ts.filter((pl.col("team") == "AAA") & (pl.col("season") == 2024)).row(0, named=True)
    assert aaa_2024["head_coach"] == "Steady Hand"
    assert aaa_2024["primary_qb_id"] == "QB-A1"
    assert aaa_2024["team_coach_changed"] is False


def test_team_coach_and_qb_change_detected() -> None:
    ts = ct.build_team_seasons()
    bbb_2024 = ts.filter((pl.col("team") == "BBB") & (pl.col("season") == 2024)).row(0, named=True)
    assert bbb_2024["team_coach_changed"] is True
    assert bbb_2024["team_qb_changed"] is True


def test_first_season_change_flags_are_null_not_false() -> None:
    """No prior season means unknown, which must not be reported as 'nothing changed'."""
    ts = ct.build_team_seasons()
    aaa_2023 = ts.filter((pl.col("team") == "AAA") & (pl.col("season") == 2023)).row(0, named=True)
    assert aaa_2023["team_coach_changed"] is None
    assert aaa_2023["team_qb_changed"] is None


def test_stable_player_has_no_situation_change() -> None:
    df = ct.build_context_table(write=False)
    row = df.filter((pl.col("player_id") == "P-STAY") & (pl.col("season") == 2024)).row(named=True)
    assert row["team_changed"] is False
    assert row["coach_changed"] is False
    assert row["qb_changed"] is False
    assert row["prior_team"] == "AAA"
    assert row["prior_targets"] == 30


def test_moving_player_inherits_new_staff_comparison() -> None:
    """coach_changed compares against the staff he actually played for, not his new team's."""
    df = ct.build_context_table(write=False)
    row = df.filter((pl.col("player_id") == "P-MOVE") & (pl.col("season") == 2024)).row(named=True)
    assert row["team_changed"] is True
    assert row["prior_player_coach"] == "Steady Hand"
    assert row["head_coach"] == "New Coach"
    assert row["coach_changed"] is True
    assert row["qb_changed"] is True


def test_vacated_share_counts_only_departed_players() -> None:
    """AAA loses P-GONE (60 targets) and P-MOVE (30) of 120; P-STAY's 30 stay."""
    df = ct.build_context_table(write=False)
    row = df.filter((pl.col("player_id") == "P-STAY") & (pl.col("season") == 2024)).row(named=True)
    assert row["vacated_target_share"] == pytest.approx(90 / 120)


def test_modal_team_survives_midseason_trade() -> None:
    """A player traded mid-season is credited to the team he played the most games for."""
    weekly = _weekly()
    traded = pl.DataFrame(
        [
            {
                "player_id": "P-TRADE",
                "player_display_name": "Deadline Deal",
                "position": "RB",
                "recent_team": team,
                "season": 2024,
                "week": week,
                "season_type": "REG",
                "targets": 1,
                "carries": 5,
                "receptions": 1,
                "target_share": 0.1,
                "air_yards_share": 0.1,
                "wopr": 0.2,
            }
            for team, week in (("AAA", 1), ("BBB", 2), ("BBB", 3))
        ]
    )
    combined = pl.concat([weekly, traded], how="diagonal_relaxed")
    players = ct._player_seasons(combined)
    row = players.filter(pl.col("player_id") == "P-TRADE").row(0, named=True)
    assert row["team"] == "BBB"
    assert row["games"] == 3
