from __future__ import annotations

import math

from sleeper_ffm.evals import stats


def test_bootstrap_ci_brackets_the_true_mean() -> None:
    values = [10.0] * 50 + [20.0] * 50  # mean 15
    low, high = stats.bootstrap_mean_ci(values, seed=1)
    assert low < 15.0 < high
    assert high - low < 5.0  # a tight-ish interval for n=100


def test_bootstrap_ci_edge_cases() -> None:
    assert all(math.isnan(x) for x in stats.bootstrap_mean_ci([]))
    assert stats.bootstrap_mean_ci([7.0]) == (7.0, 7.0)


def test_bootstrap_is_deterministic_under_seed() -> None:
    v = [1.0, 5.0, 2.0, 8.0, 3.0]
    assert stats.bootstrap_mean_ci(v, seed=42) == stats.bootstrap_mean_ci(v, seed=42)


def test_paired_diff_ci_excludes_zero_when_one_side_dominates() -> None:
    a = [10.0, 11.0, 12.0, 13.0, 14.0]
    b = [1.0, 2.0, 3.0, 4.0, 5.0]  # a beats b by 9 every pair
    low, _high = stats.paired_diff_ci(a, b, seed=3)
    assert low > 0  # the engine genuinely wins


def test_paired_diff_ci_straddles_zero_when_tied() -> None:
    a = [5.0, 3.0, 8.0, 2.0]
    b = [4.0, 4.0, 7.0, 3.0]  # noisy, no real edge
    low, high = stats.paired_diff_ci(a, b, seed=3)
    assert low < 0 < high


def test_paired_diff_length_mismatch_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="differ in length"):
        stats.paired_diff_ci([1.0, 2.0], [1.0])


def test_sign_test_a_coinflip_is_not_significant() -> None:
    assert stats.sign_test_pvalue(5, 10) == 1.0  # exactly half


def test_sign_test_a_sweep_is_significant() -> None:
    assert stats.sign_test_pvalue(10, 10) < 0.01  # winning every game
    assert stats.sign_test_pvalue(0, 10) < 0.01  # losing every game (two-sided)


def test_sign_test_symmetry_and_bounds() -> None:
    assert stats.sign_test_pvalue(3, 10) == stats.sign_test_pvalue(7, 10)
    assert stats.sign_test_pvalue(0, 0) == 1.0
    assert 0.0 <= stats.sign_test_pvalue(9, 15) <= 1.0
