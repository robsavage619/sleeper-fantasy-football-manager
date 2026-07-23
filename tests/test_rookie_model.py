"""S6 rookie-model tests (synthetic frames — no network, no cached parquet)."""

from __future__ import annotations

import polars as pl
import pytest

import sleeper_ffm.model.research.rookie_model as rm


def test_wilson_interval_brackets_the_estimate() -> None:
    low, high = rm.wilson_interval(50, 100)
    assert low < 0.5 < high
    assert 0.39 < low < 0.41
    assert 0.59 < high < 0.61


def test_wilson_interval_stays_in_bounds_at_the_extremes() -> None:
    """The normal approximation goes negative at 0 hits; Wilson must not."""
    low, high = rm.wilson_interval(0, 30)
    assert low == 0.0
    assert 0.0 < high < 0.2

    low, high = rm.wilson_interval(30, 30)
    assert high == 1.0
    assert 0.8 < low < 1.0


def test_wilson_interval_handles_empty_cell() -> None:
    assert rm.wilson_interval(0, 0) == (0.0, 0.0)


def test_undrafted_players_stay_in_the_cohort(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undrafted players are the denominator's largest group; losing them inflates rates."""
    id_map = pl.DataFrame(
        [
            {
                "gsis_id": "drafted",
                "name": "First Rounder",
                "position": "WR",
                "draft_year": 2020.0,
                "draft_round": 1.0,
                "draft_ovr": 5.0,
            },
            {
                "gsis_id": "undrafted",
                "name": "Free Agent",
                "position": "WR",
                "draft_year": 2020.0,
                "draft_round": None,
                "draft_ovr": None,
            },
        ]
    )
    monkeypatch.setattr(rm, "load_id_map", lambda: id_map)

    cohort = rm.draft_cohort([2020])
    assert cohort.height == 2
    buckets = dict(zip(cohort["gsis_id"], cohort["bucket"], strict=True))
    assert buckets["drafted"] == 1
    assert buckets["undrafted"] == rm.UNDRAFTED_ROUND


def test_player_who_never_played_counts_as_a_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    """The survivorship guard: no stats must mean a recorded failure, not a dropped row."""
    id_map = pl.DataFrame(
        [
            {
                "gsis_id": pid,
                "name": pid,
                "position": "WR",
                "draft_year": 2020.0,
                "draft_round": 1.0,
                "draft_ovr": 5.0,
            }
            for pid in ("played", "never_played")
        ]
    )
    totals = pl.DataFrame(
        [
            {
                "gsis_id": "played",
                "season": 2020,
                "position": "WR",
                "season_fp": 250.0,
            }
        ]
    )
    monkeypatch.setattr(rm, "load_id_map", lambda: id_map)
    monkeypatch.setattr(rm, "compute_season_totals", lambda seasons=None: totals)
    monkeypatch.setattr(rm, "replacement_thresholds", lambda _t: {"WR": 100.0})

    out = rm.cohort_outcomes([2020], horizon=1)
    assert out.height == 2
    by_id = {r["gsis_id"]: r for r in out.iter_rows(named=True)}
    assert by_id["played"]["hit"] is True
    assert by_id["never_played"]["hit"] is False
    assert by_id["never_played"]["best_fp"] == 0.0


def test_replacement_line_is_applied_per_season(monkeypatch: pytest.MonkeyPatch) -> None:
    """A player must be judged against his own season's line, not a pooled one."""
    id_map = pl.DataFrame(
        [
            {
                "gsis_id": "wr1",
                "name": "wr1",
                "position": "WR",
                "draft_year": 2020.0,
                "draft_round": 2.0,
                "draft_ovr": 40.0,
            }
        ]
    )
    # 120 points clears a weak 2021 line but not a strong 2020 one.
    totals_by_season = {
        2020: pl.DataFrame(
            [{"gsis_id": "wr1", "season": 2020, "position": "WR", "season_fp": 80.0}]
        ),
        2021: pl.DataFrame(
            [{"gsis_id": "wr1", "season": 2021, "position": "WR", "season_fp": 120.0}]
        ),
    }
    lines = {2020: {"WR": 200.0}, 2021: {"WR": 100.0}}
    seen: list[int] = []

    def _totals(seasons=None):
        season = seasons[0]
        seen.append(season)
        return totals_by_season[season]

    monkeypatch.setattr(rm, "load_id_map", lambda: id_map)
    monkeypatch.setattr(rm, "compute_season_totals", _totals)
    monkeypatch.setattr(rm, "replacement_thresholds", lambda t: lines[int(t["season"][0])])

    out = rm.cohort_outcomes([2020], horizon=2)
    assert seen == [2020, 2021]  # each season priced on its own
    assert out.row(0, named=True)["hit"] is True


def test_hit_rates_report_every_bucket_present() -> None:
    outcomes = pl.DataFrame(
        {
            "gsis_id": ["a", "b", "c", "d"],
            "position": ["WR", "WR", "RB", "RB"],
            "bucket": [1, 1, 8, 8],
            "hit": [True, False, False, False],
        }
    )
    rates = {(r.position, r.bucket): r for r in rm.hit_rates(outcomes)}
    assert rates[("WR", 1)].rate == pytest.approx(0.5)
    assert rates[("RB", 8)].rate == pytest.approx(0.0)
    assert rates[("ALL", 1)].n == 2
