"""S2 situation-change tests (synthetic context table — no cached parquet)."""

from __future__ import annotations

import polars as pl
import pytest

import sleeper_ffm.model.research.situation_changes as sc


def _context(rows: list[dict[str, object]]) -> pl.DataFrame:
    defaults: dict[str, object] = {
        "position": "WR",
        "season": 2020,
        "games": 12,
        "prior_games": 12,
        "prior_team": "AAA",
        "team_changed": False,
        "coach_changed": False,
        "qb_changed": False,
        "target_share": 0.15,
        "prior_target_share": 0.15,
        "air_yards_share": 0.20,
        "prior_air_yards_share": 0.20,
        "wopr": 0.50,
        "prior_wopr": 0.50,
        "vacated_target_share": 0.10,
        "season_age": 26.0,
    }
    return pl.DataFrame([{**defaults, **r} for r in rows])


def test_eligible_pairs_drops_short_and_first_seasons(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _context(
        [
            {"player_id": "ok"},
            {"player_id": "short", "games": 3},
            {"player_id": "short_prior", "prior_games": 2},
            {"player_id": "rookie", "prior_team": None},
        ]
    )
    monkeypatch.setattr(sc, "load_context_table", lambda: df)
    kept = sc.eligible_pairs()["player_id"].to_list()
    assert kept == ["ok"]


def test_carryover_separates_changed_from_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Movers carry usage through unchanged; stayers invert it. Groups must not mix."""
    rows: list[dict[str, object]] = []
    for i in range(6):
        share = 0.10 + i * 0.02
        rows.append(
            {
                "player_id": f"moved{i}",
                "team_changed": True,
                "prior_target_share": share,
                "target_share": share,
            }
        )
        rows.append(
            {
                "player_id": f"stayed{i}",
                "team_changed": False,
                "prior_target_share": share,
                "target_share": 0.22 - share,
            }
        )
    monkeypatch.setattr(sc, "load_context_table", lambda: _context(rows))

    results = sc.usage_carryover(positions=("WR",))
    by_group = {
        (r.group, r.position): r
        for r in results
        if r.metric == "target_share" and r.change == "team_changed"
    }
    assert by_group[("changed", "WR")].correlation == pytest.approx(1.0)
    assert by_group[("stable", "WR")].correlation == pytest.approx(-1.0)


def test_summarize_reports_gap_between_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    results = [
        sc.CarryoverResult("target_share", "team_changed", "RB", "changed", 50, 0.35),
        sc.CarryoverResult("target_share", "team_changed", "RB", "stable", 200, 0.70),
    ]
    table = sc.summarize(results)
    row = table.row(0, named=True)
    assert row["r_changed"] == pytest.approx(0.35)
    assert row["r_stable"] == pytest.approx(0.70)
    assert row["gap"] == pytest.approx(-0.35)


def test_vacated_effect_uses_movers_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stayers must not enter the vacated-opportunity estimate."""
    rows: list[dict[str, object]] = []
    for i in range(5):
        rows.append(
            {
                "player_id": f"moved{i}",
                "team_changed": True,
                "vacated_target_share": 0.05 * i,
                "target_share": 0.05 * i,
                "prior_target_share": 0.15,
            }
        )
    for i in range(20):
        rows.append(
            {
                "player_id": f"stayed{i}",
                "team_changed": False,
                "vacated_target_share": 0.4,
                "target_share": 0.01,
                "prior_target_share": 0.01,
            }
        )
    monkeypatch.setattr(sc, "load_context_table", lambda: _context(rows))

    out = sc.vacated_opportunity_effect(position="WR")
    assert out["n"] == 5
    assert out["r_vacated_share"] == pytest.approx(1.0)


def test_empty_context_table_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sc, "load_context_table", lambda: pl.DataFrame())
    assert sc.usage_carryover() == []
    assert sc.vacated_opportunity_effect() == {}
    assert sc.summarize([]).is_empty()
