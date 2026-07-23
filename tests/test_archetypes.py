"""S4 archetype tests (synthetic frames — no network, no cached parquet)."""

from __future__ import annotations

import polars as pl
import pytest

import sleeper_ffm.model.research.archetypes as arch


def _usage(rows: list[dict[str, object]]) -> pl.DataFrame:
    defaults: dict[str, object] = {
        "player_id": "p1",
        "season": 2020,
        "position": "RB",
        "name": "p1",
        "games": 12,
        "fp": 120.0,
        "fp_per_game": 10.0,
        "targets": 20,
        "carries": 180,
        "rec_yards": 150.0,
        "receptions": 15,
        "season_age": 25.0,
    }
    return pl.DataFrame([{**defaults, **r} for r in rows])


def test_archetype_splits_at_the_position_median() -> None:
    """A median split must produce balanced groups regardless of the scale of the metric."""
    rows = [
        {"player_id": f"rb{i}", "targets": i * 10, "carries": 200 - i * 10} for i in range(1, 11)
    ]
    labelled = arch.assign_archetypes(_usage(rows))
    counts = labelled.group_by("archetype").len().to_dicts()
    sizes = sorted(c["len"] for c in counts)
    assert sizes == [5, 5]


def test_receiving_backs_labelled_by_target_share() -> None:
    rows = [
        {"player_id": "catcher", "targets": 90, "carries": 30},
        {"player_id": "runner", "targets": 5, "carries": 250},
    ]
    labelled = arch.assign_archetypes(_usage(rows))
    by_id = {r["player_id"]: r["archetype"] for r in labelled.iter_rows(named=True)}
    assert by_id["catcher"] == "receiving_back"
    assert by_id["runner"] == "grinder"


def test_within_player_change_differences_the_same_player() -> None:
    """The whole point is that the player is his own baseline across two seasons."""
    rows = [
        {"player_id": "a", "season": 2020, "fp_per_game": 12.0, "season_age": 26.0},
        {"player_id": "a", "season": 2021, "fp_per_game": 9.0, "season_age": 27.0},
    ]
    labelled = arch.assign_archetypes(_usage(rows))
    changes = arch.within_player_change(labelled)
    assert changes.height == 1
    assert changes.row(0, named=True)["d_fp_per_game"] == pytest.approx(-3.0)


def test_within_player_change_ignores_non_consecutive_seasons() -> None:
    rows = [
        {"player_id": "a", "season": 2020, "fp_per_game": 12.0, "season_age": 26.0},
        {"player_id": "a", "season": 2022, "fp_per_game": 9.0, "season_age": 28.0},
    ]
    labelled = arch.assign_archetypes(_usage(rows))
    assert arch.within_player_change(labelled).is_empty()


def test_attrition_marks_players_without_a_next_season() -> None:
    rows = [
        {"player_id": "survivor", "season": 2020, "season_age": 26.0},
        {"player_id": "survivor", "season": 2021, "season_age": 27.0},
        {"player_id": "gone", "season": 2020, "season_age": 26.0},
    ]
    labelled = arch.assign_archetypes(_usage(rows))
    rates = arch.attrition_rate(labelled)
    # Only 2020 is evaluated; 2021 is the last season and is excluded.
    total = rates.select(pl.col("n").sum()).item()
    assert total == 2
    weighted = (rates["attrition_rate"] * rates["n"]).sum() / total
    assert weighted == pytest.approx(0.5)


def test_attrition_excludes_the_final_season(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every player in the last season lacks a successor and would read as 100% death."""
    rows = [
        {"player_id": "a", "season": 2020, "season_age": 26.0},
        {"player_id": "a", "season": 2021, "season_age": 27.0},
    ]
    labelled = arch.assign_archetypes(_usage(rows))
    rates = arch.attrition_rate(labelled)
    assert rates.select(pl.col("n").sum()).item() == 1
    assert rates["attrition_rate"].to_list() == [0.0]


def test_empty_input_returns_empty() -> None:
    assert arch.assign_archetypes(pl.DataFrame()).is_empty()
    assert arch.within_player_change(pl.DataFrame()).is_empty()
    assert arch.attrition_rate(pl.DataFrame()).is_empty()
    assert arch.aging_curve(pl.DataFrame()) == []
