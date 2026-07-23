"""Out-of-sample backtests — substantiate docstring claims rather than asserting them.

Yard-line and age-curve backtests read only the on-disk nflverse parquet cache (2024 +
2025) and skip cleanly if that cache is absent. The season-sim backtest requires live
Sleeper API calls (see its docstring for why no on-disk cache exists) and skips
cleanly on any network/data unavailability, same pattern as test_reconciliation.py.
"""

from __future__ import annotations

import pytest

from sleeper_ffm.evals.backtest import (
    BacktestUnavailableError,
    run_age_curve_backtest,
    run_season_sim_backtest,
    run_yardline_backtest,
    trade_acceptance_validation_status,
)


def test_yardline_beats_yardage_out_of_sample() -> None:
    try:
        result = run_yardline_backtest(train_season=2024, eval_season=2025)
    except BacktestUnavailableError as exc:
        pytest.skip(f"backtest data unavailable: {exc}")

    assert result.n_players > 50, "too few players for a meaningful backtest"
    # The core claim: opportunity-priced MAE is strictly lower than the yardage baseline.
    assert result.mae_yardline < result.mae_yardage
    assert result.improvement_pct > 5.0  # docstrings cite ~25%; guard well below that


# ---------------------------------------------------------------------------
# Age-curve backtest — real out-of-sample check, hermetic (cache-only)
# ---------------------------------------------------------------------------


def test_age_curve_beats_naive_flat_carry_out_of_sample() -> None:
    try:
        result = run_age_curve_backtest(train_season=2024, eval_season=2025)
    except BacktestUnavailableError as exc:
        pytest.skip(f"backtest data unavailable: {exc}")

    assert result.n_players > 30, "too few players for a meaningful backtest"
    # The core claim: one year of age-curve adjustment beats assuming no aging at all.
    assert result.mae_age_curve < result.mae_naive_flat
    assert result.improvement_pct > 0.0
    # Directional calibration should beat a coin flip by a real margin, not just noise.
    assert result.n_directional > 20
    assert result.direction_hit_rate > 0.55


def test_age_curve_result_is_deterministic() -> None:
    try:
        first = run_age_curve_backtest(train_season=2024, eval_season=2025)
        second = run_age_curve_backtest(train_season=2024, eval_season=2025)
    except BacktestUnavailableError as exc:
        pytest.skip(f"backtest data unavailable: {exc}")

    assert first == second


def test_age_curve_backtest_unavailable_for_uncached_seasons() -> None:
    with pytest.raises(BacktestUnavailableError):
        run_age_curve_backtest(train_season=1901, eval_season=1902)


# ---------------------------------------------------------------------------
# Trade acceptance — documents the absence of ground truth, doesn't fake a number
# ---------------------------------------------------------------------------


def test_trade_acceptance_validation_status_reports_no_ground_truth(monkeypatch) -> None:
    import sleeper_ffm.model.offer_log as offer_log_module

    monkeypatch.setattr(offer_log_module, "list_offers", lambda: [])

    status = trade_acceptance_validation_status()
    assert status["validated"] is False
    assert "no accepted/rejected/countered outcome field" in status["reason"]


def test_trade_acceptance_validation_status_flips_if_outcomes_appear(monkeypatch) -> None:
    import sleeper_ffm.model.offer_log as offer_log_module

    monkeypatch.setattr(
        offer_log_module,
        "list_offers",
        lambda: [{"offer_id": "1", "sent": True, "outcome": "accepted"}],
    )

    status = trade_acceptance_validation_status()
    assert status["validated"] is True


# ---------------------------------------------------------------------------
# Season-sim backtest — single-season sanity check against a realized bracket
# ---------------------------------------------------------------------------


def test_season_sim_backtest_against_realized_2024_bracket() -> None:
    try:
        result = run_season_sim_backtest("2024")
    except BacktestUnavailableError as exc:
        pytest.skip(f"season-sim backtest unavailable (network/data): {exc}")

    assert result.n_teams >= 4
    assert result.playoff_teams >= 2
    # Sanity, not calibration (see docstring): the champion must be a real roster_id
    # that appears among the simulated teams, with a odds value in [0, 1].
    assert 0.0 <= result.champion_title_odds <= 1.0
    assert 1 <= result.champion_odds_rank <= result.n_teams
    assert 0 <= result.playoff_field_predicted_correctly <= result.playoff_teams
