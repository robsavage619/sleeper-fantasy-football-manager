from __future__ import annotations

import pytest

from sleeper_ffm.evals import gap_report

# 1QB/1RB/1WR/1FLEX, mirroring test_arena's pure-logic layout.
_SLOTS = ["QB", "RB", "WR", "FLEX", "BN", "BN"]
_POS = {
    "qb1": "QB",
    "qb2": "QB",
    "rb1": "RB",
    "rb2": "RB",
    "wr1": "WR",
    "wr2": "WR",
    "te1": "TE",
    "k1": "K",
    "k2": "K",
}


def _loss_sum(buckets: list[tuple[str, float]]) -> float:
    return sum(loss for _, loss in buckets)


def test_identical_lineups_decompose_to_nothing() -> None:
    started = ["qb1", "rb1", "wr1", "te1"]
    pts = {"qb1": 20.0, "rb1": 15.0, "wr1": 10.0, "te1": 8.0}
    assert gap_report.decompose_loss(started, started, pts, _POS, frozenset()) == []


def test_dead_starter_bucket_wins_over_position_tags() -> None:
    # Started rb2 who scored 0.0; optimal had rb1. Same position, but the zero is the story.
    out = gap_report.decompose_loss(
        ["qb1", "rb2", "wr1", "te1"],
        ["qb1", "rb1", "wr1", "te1"],
        {"qb1": 20.0, "rb1": 12.0, "rb2": 0.0, "wr1": 10.0, "te1": 8.0},
        _POS,
        frozenset(),
    )
    assert out == [("dead_starter", 12.0)]


def test_flagged_bench_beats_rank_inversion() -> None:
    # Sat rb1 (flagged Questionable that week) who outscored the started rb2.
    out = gap_report.decompose_loss(
        ["qb1", "rb2", "wr1", "te1"],
        ["qb1", "rb1", "wr1", "te1"],
        {"qb1": 20.0, "rb1": 18.0, "rb2": 6.0, "wr1": 10.0, "te1": 8.0},
        _POS,
        frozenset({"rb1"}),
    )
    assert out == [("benched_flagged", 12.0)]


def test_same_position_miss_among_healthy_players_is_rank_inversion() -> None:
    out = gap_report.decompose_loss(
        ["qb1", "rb2", "wr1", "te1"],
        ["qb1", "rb1", "wr1", "te1"],
        {"qb1": 20.0, "rb1": 18.0, "rb2": 6.0, "wr1": 10.0, "te1": 8.0},
        _POS,
        frozenset(),
    )
    assert out == [("rank_inversion", 12.0)]


def test_cross_position_pair_is_a_flex_call() -> None:
    # Started wr2 in FLEX; optimal flexed te1 instead. Different positions → flex_cross.
    out = gap_report.decompose_loss(
        ["qb1", "rb1", "wr1", "wr2"],
        ["qb1", "rb1", "wr1", "te1"],
        {"qb1": 20.0, "rb1": 15.0, "wr1": 10.0, "wr2": 5.0, "te1": 9.0},
        _POS,
        frozenset(),
    )
    assert out == [("flex_cross", 4.0)]


def test_kdef_bucket_tags_kicker_and_defense_calls() -> None:
    out = gap_report.decompose_loss(
        ["k2"],
        ["k1"],
        {"k1": 12.0, "k2": 3.0},
        _POS,
        frozenset(),
    )
    assert out == [("kdef", 9.0)]


def test_unfilled_slot_charges_the_missed_points() -> None:
    # Manager left the FLEX empty; optimal filled it with te1.
    out = gap_report.decompose_loss(
        ["qb1", "rb1", "wr1"],
        ["qb1", "rb1", "wr1", "te1"],
        {"qb1": 20.0, "rb1": 15.0, "wr1": 10.0, "te1": 9.0},
        _POS,
        frozenset(),
    )
    assert out == [("unfilled", 9.0)]


def test_decomposition_is_exact_on_a_messy_multi_swap_week() -> None:
    # Three simultaneous misses: a dead starter, a FLEX call, and a benched-flagged QB.
    started = ["qb2", "rb2", "wr1", "wr2"]
    optimal = ["qb1", "rb1", "wr1", "te1"]
    pts = {
        "qb1": 25.0,
        "qb2": 10.0,
        "rb1": 14.0,
        "rb2": 0.0,
        "wr1": 12.0,
        "wr2": 4.0,
        "te1": 9.0,
    }
    out = gap_report.decompose_loss(started, optimal, pts, _POS, frozenset({"qb1"}))
    started_pts = sum(pts[p] for p in started)
    optimal_pts = sum(pts[p] for p in optimal)
    assert _loss_sum(out) == pytest.approx(optimal_pts - started_pts)
    assert ("dead_starter", 14.0) in out  # rb2 (0.0) paired with rb1
    assert ("benched_flagged", 15.0) in out  # qb2 started over flagged qb1


def test_merge_pools_points_and_counts() -> None:
    a = gap_report.GapReport(
        season=2022,
        league_id="L",
        projector="p",
        n_roster_weeks=10,
        optimal_total=1000.0,
        engine_total=800.0,
        actual_total=850.0,
        engine_loss={"dead_starter": 120.0},
        engine_pairs={"dead_starter": 8},
        actual_loss={"dead_starter": 60.0},
        actual_pairs={"dead_starter": 4},
        identical_lineups=3,
    )
    b = gap_report.GapReport(
        season=2023,
        league_id="L",
        projector="p",
        n_roster_weeks=10,
        optimal_total=1000.0,
        engine_total=820.0,
        actual_total=840.0,
        engine_loss={"rank_inversion": 80.0},
        engine_pairs={"rank_inversion": 12},
        actual_loss={"rank_inversion": 90.0},
        actual_pairs={"rank_inversion": 11},
        identical_lineups=2,
    )
    pooled = gap_report.merge_gap_reports([a, b])
    assert pooled.n_roster_weeks == 20
    assert pooled.optimal_total == 2000.0
    assert pooled.engine_loss["dead_starter"] == 120.0
    assert pooled.engine_loss["rank_inversion"] == 80.0
    assert pooled.actual_pairs["rank_inversion"] == 11
    assert pooled.identical_lineups == 5
    assert "pooled" in pooled.table()


def test_mean_capture_matches_totals() -> None:
    r = gap_report.GapReport(
        season=2024,
        league_id="L",
        projector="p",
        n_roster_weeks=1,
        optimal_total=100.0,
        engine_total=81.0,
        actual_total=84.0,
    )
    assert gap_report.mean_capture(r) == (0.81, 0.84)


def test_table_renders_every_bucket_row() -> None:
    r = gap_report.GapReport(
        season=2024,
        league_id="L",
        projector="engine",
        n_roster_weeks=5,
        optimal_total=500.0,
        engine_total=400.0,
        actual_total=420.0,
        engine_loss={"dead_starter": 50.0, "rank_inversion": 50.0},
        engine_pairs={"dead_starter": 3, "rank_inversion": 5},
    )
    table = r.table()
    for bucket in gap_report.BUCKETS:
        assert bucket in table
    assert "80.00%" in table  # engine capture
    assert "84.00%" in table  # manager capture
