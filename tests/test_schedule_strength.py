"""Tests for DvP + SoS (pure helpers — no network)."""

from __future__ import annotations

import polars as pl

from sleeper_ffm.model.schedule_strength import (
    PLAYOFF_WEEKS,
    compute_dvp,
    schedule_softness,
)


def _scored(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "season": pl.Int64,
            "week": pl.Int64,
            "position": pl.Utf8,
            "opponent_team": pl.Utf8,
            "fp_sffm": pl.Float64,
        },
    )


def test_compute_dvp_indexes_against_league_average() -> None:
    # Two defenses face RBs over 4 games each. SOFT allows double the points TOUGH does.
    rows = []
    for wk in range(1, 5):
        rows.append(
            {"season": 2025, "week": wk, "position": "RB", "opponent_team": "SOFT", "fp_sffm": 30.0}
        )
        rows.append(
            {
                "season": 2025,
                "week": wk,
                "position": "RB",
                "opponent_team": "TOUGH",
                "fp_sffm": 10.0,
            }
        )
    dvp = compute_dvp(_scored(rows))
    # League avg allowed = 20; SOFT=30 -> 1.5, TOUGH=10 -> 0.5.
    assert dvp[("SOFT", "RB")] == 1.5
    assert dvp[("TOUGH", "RB")] == 0.5


def test_compute_dvp_requires_min_games() -> None:
    rows = [
        {"season": 2025, "week": 1, "position": "WR", "opponent_team": "X", "fp_sffm": 40.0},
        {"season": 2025, "week": 2, "position": "WR", "opponent_team": "X", "fp_sffm": 40.0},
    ]  # only 2 games — below _MIN_DEF_GAMES
    assert compute_dvp(_scored(rows)) == {}


def test_schedule_softness_averages_opponent_indices() -> None:
    dvp = {("SOFT", "RB"): 1.5, ("TOUGH", "RB"): 0.5}
    opps = [(1, "SOFT"), (2, "TOUGH"), (3, "SOFT")]
    idx, n = schedule_softness(opps, "RB", dvp)
    assert n == 3
    assert idx == round((1.5 + 0.5 + 1.5) / 3, 3)


def test_schedule_softness_unknown_opponent_is_neutral() -> None:
    dvp = {("SOFT", "RB"): 1.5}
    idx, n = schedule_softness([(1, "SOFT"), (2, "UNKNOWN")], "RB", dvp)
    assert n == 2
    assert idx == round((1.5 + 1.0) / 2, 3)  # UNKNOWN defaults to 1.0


def test_schedule_softness_playoff_weeks_filter() -> None:
    dvp = {("SOFT", "RB"): 1.5, ("TOUGH", "RB"): 0.5}
    opps = [(1, "TOUGH"), (PLAYOFF_WEEKS[0], "SOFT"), (PLAYOFF_WEEKS[1], "SOFT")]
    idx, n = schedule_softness(opps, "RB", dvp, weeks=PLAYOFF_WEEKS)
    assert n == 2  # only the two playoff-week games count
    assert idx == 1.5


def test_compute_dvp_empty_input() -> None:
    assert compute_dvp(_scored([])) == {}


# --- Elo strength-of-schedule (pure helper — no network) ----------------------------


def test_elo_sos_rates_playoff_opponent_strength(monkeypatch) -> None:
    from sleeper_ffm.model import schedule_strength as ss
    from sleeper_ffm.model.elo import EloBoard, TeamRating

    board = EloBoard(
        ratings=[
            TeamRating("AAA", 1500.0, 10, 2025, 18),
            TeamRating("STRONG", 1700.0, 10, 2025, 18),
            TeamRating("WEAK", 1300.0, 10, 2025, 18),
        ]
    )
    monkeypatch.setattr("sleeper_ffm.model.elo.build_elo", lambda *a, **k: board)

    # AAA plays WEAK in the regular weeks and STRONG in every playoff week.
    scheds = {"AAA": [(14, "WEAK"), (15, "STRONG"), (16, "STRONG"), (17, "STRONG")]}
    out = ss._elo_schedule_strength(scheds)
    assert len(out) == 1
    entry = out[0]
    assert entry.team == "AAA" and entry.elo == 1500.0
    assert entry.playoff_opp_elo == 1700.0  # all three playoff opponents are STRONG
    assert entry.playoff_weeks_counted == 3
    assert entry.playoff_difficulty > 1.0  # tougher than the league mean
    # Full-season mean pulls in the WEAK regular-week game, so it sits below the playoff mean.
    assert entry.full_season_opp_elo < entry.playoff_opp_elo


def test_elo_sos_returns_empty_when_board_is_empty(monkeypatch) -> None:
    from sleeper_ffm.model import schedule_strength as ss
    from sleeper_ffm.model.elo import EloBoard

    monkeypatch.setattr("sleeper_ffm.model.elo.build_elo", lambda *a, **k: EloBoard())
    assert ss._elo_schedule_strength({"AAA": [(15, "BBB")]}) == []


def test_elo_sos_survives_a_build_failure(monkeypatch) -> None:
    from sleeper_ffm.model import schedule_strength as ss

    def _boom(*a, **k):
        raise RuntimeError("schedule cache missing")

    monkeypatch.setattr("sleeper_ffm.model.elo.build_elo", _boom)
    assert ss._elo_schedule_strength({"AAA": [(15, "BBB")]}) == []
