"""Red-zone expected-TD backtest — substantiates the docstrings' out-of-sample claim.

Reads the on-disk nflverse parquet cache (2024 + 2025). Skips cleanly if that cache is
absent so the suite stays green in a data-less checkout.
"""

from __future__ import annotations

import pytest

from sleeper_ffm.evals.backtest import BacktestUnavailableError, run_redzone_backtest


def test_redzone_beats_yardage_out_of_sample() -> None:
    try:
        result = run_redzone_backtest(train_season=2024, eval_season=2025)
    except BacktestUnavailableError as exc:
        pytest.skip(f"backtest data unavailable: {exc}")

    assert result.n_players > 50, "too few players for a meaningful backtest"
    # The core claim: red-zone-opportunity MAE is strictly lower than the yardage baseline.
    assert result.mae_redzone < result.mae_yardage
    assert result.improvement_pct > 5.0  # docstrings cite ~19%; guard well below that
