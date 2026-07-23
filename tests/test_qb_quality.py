"""S3 quarterback-quality tests (synthetic frames — no network, no cached parquet)."""

from __future__ import annotations

import polars as pl
import pytest

import sleeper_ffm.model.research.qb_quality as qq


def _ngs(rows: list[dict[str, object]]) -> pl.DataFrame:
    defaults: dict[str, object] = {
        "week": 0,
        "season": 2021,
        "player_gsis_id": "qb1",
        "completion_percentage_above_expectation": 2.0,
        "attempts": 400,
    }
    return pl.DataFrame([{**defaults, **r} for r in rows])


def test_qb_quality_uses_season_aggregate_row_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """NGS ships weekly rows alongside a week-0 season aggregate; only the latter is a season."""
    ngs = _ngs(
        [
            {"week": 0, "completion_percentage_above_expectation": 3.0},
            {"week": 5, "completion_percentage_above_expectation": -9.0},
        ]
    )
    monkeypatch.setattr(qq, "load_ngs", lambda stat_type, seasons=None: ngs)

    out = qq.qb_season_quality([2021])
    assert out.height == 1
    assert out["cpoe"].to_list() == [3.0]


def test_low_volume_quarterbacks_are_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    ngs = _ngs(
        [
            {"player_gsis_id": "starter", "attempts": 500},
            {"player_gsis_id": "backup", "attempts": 20},
        ]
    )
    monkeypatch.setattr(qq, "load_ngs", lambda stat_type, seasons=None: ngs)

    assert qq.qb_season_quality([2021])["player_id"].to_list() == ["starter"]


def test_effect_recovers_a_known_slope() -> None:
    """A panel built with a planted slope must be recovered by the estimator."""
    slope = 0.05
    rows = []
    for i in range(30):
        d_cpoe = (i - 15) * 0.4
        rows.append(
            {
                "player_id": f"wr{i}",
                "season": 2021,
                "position": "WR",
                "d_cpoe": d_cpoe,
                "d_fp_per_target": slope * d_cpoe,
                "targets_per_game": 6.0,
            }
        )
    panel = pl.DataFrame(rows)

    results = {e.position: e for e in qq.estimate_effect(panel)}
    assert results["WR"].slope == pytest.approx(slope, abs=1e-6)
    assert results["WR"].correlation == pytest.approx(1.0)


def test_no_relationship_reports_zero_not_noise() -> None:
    """A flat outcome must come back as no effect rather than a spurious slope."""
    panel = pl.DataFrame(
        {
            "player_id": [f"wr{i}" for i in range(20)],
            "season": [2021] * 20,
            "position": ["WR"] * 20,
            "d_cpoe": [float(i - 10) for i in range(20)],
            "d_fp_per_target": [0.0] * 20,
            "targets_per_game": [6.0] * 20,
        }
    )
    results = {e.position: e for e in qq.estimate_effect(panel)}
    assert results["WR"].slope == pytest.approx(0.0)


def test_empty_sources_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qq, "load_context_table", lambda: pl.DataFrame())
    assert qq.build_panel([2021]).is_empty()
    assert qq.estimate_effect(pl.DataFrame()) == []


def test_team_qb_context_scales_by_standard_deviation(monkeypatch: pytest.MonkeyPatch) -> None:
    """A QB one SD above the mean is worth the per-SD figure to his receivers."""
    quality = pl.DataFrame(
        {
            "player_id": ["good", "avg", "bad"],
            "season": [2025, 2025, 2025],
            "cpoe": [4.0, 0.0, -4.0],
            "attempts": [400, 400, 400],
        }
    )
    teams = pl.DataFrame(
        {
            "season": [2025, 2025, 2025],
            "team": ["GOOD", "AVG", "BAD"],
            "primary_qb_id": ["good", "avg", "bad"],
        }
    )
    monkeypatch.setattr(qq, "qb_season_quality", lambda seasons: quality)
    monkeypatch.setattr(
        "sleeper_ffm.model.context_table.build_team_seasons", lambda seasons=None: teams
    )

    ctx = qq.team_qb_context(2025)
    sd = 4.0  # population of {4, 0, -4} has sample sd 4.0
    assert ctx["GOOD"] == pytest.approx(4.0 / sd * qq.QB_QUALITY_PTS_PER_SD, abs=1e-3)
    assert ctx["AVG"] == pytest.approx(0.0, abs=1e-3)
    # Symmetric: a bad QB costs what a good one gives.
    assert ctx["BAD"] == pytest.approx(-ctx["GOOD"], abs=1e-3)


def test_team_qb_context_skips_teams_without_a_qualifying_qb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quality = pl.DataFrame(
        {
            "player_id": ["known"],
            "season": [2025],
            "cpoe": [2.0],
            "attempts": [400],
        }
    )
    teams = pl.DataFrame(
        {
            "season": [2025, 2025],
            "team": ["HAS", "NONE"],
            "primary_qb_id": ["known", "unknown"],
        }
    )
    monkeypatch.setattr(qq, "qb_season_quality", lambda seasons: quality)
    monkeypatch.setattr(
        "sleeper_ffm.model.context_table.build_team_seasons", lambda seasons=None: teams
    )

    ctx = qq.team_qb_context(2025)
    assert "NONE" not in ctx


def test_team_qb_context_empty_when_no_quality_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qq, "qb_season_quality", lambda seasons: pl.DataFrame())
    assert qq.team_qb_context(2025) == {}
