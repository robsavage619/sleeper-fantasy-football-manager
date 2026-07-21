"""Small, pure statistics helpers so every arena claim ships with an error bar.

The arena's headline numbers (capture %, beat-rate, a season's win-loss record) are point
estimates over a few hundred roster-weeks or a handful of games. A point estimate with no
uncertainty invites over-reading noise as signal — exactly the trap the forecast-vs-rotowire
and QB-Elo verdicts were written to avoid. These turn a point estimate into an interval or a
p-value: a bootstrap CI for means and paired differences, and a two-sided sign test for a
win-rate against a coin flip.

Deterministic by construction: the bootstrap takes a seed, so a result is reproducible and a
ledger comparison across commits is meaningful rather than jittery.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np


def bootstrap_mean_ci(
    values: Sequence[float],
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 20260720,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for the mean of ``values``.

    Args:
        values: The sample.
        n_boot: Number of bootstrap resamples.
        alpha: Two-sided miss rate (0.05 → a 95% interval).
        seed: RNG seed for reproducibility.

    Returns:
        ``(low, high)`` at the ``1 - alpha`` level. ``(nan, nan)`` for an empty sample; a
        degenerate ``(v, v)`` for a single value.
    """
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return (math.nan, math.nan)
    if arr.size == 1:
        return (float(arr[0]), float(arr[0]))
    rng = np.random.default_rng(seed)
    means = arr[rng.integers(0, arr.size, size=(n_boot, arr.size))].mean(axis=1)
    low = float(np.percentile(means, 100 * alpha / 2))
    high = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return (round(low, 4), round(high, 4))


def paired_diff_ci(
    a: Sequence[float],
    b: Sequence[float],
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 20260720,
) -> tuple[float, float]:
    """Bootstrap CI for the mean paired difference ``a[i] - b[i]``.

    Resamples the *pairs* (one index vector per bootstrap draw), so the correlation between
    the two series — engine and manager on the same roster-week — is preserved. An interval
    that excludes 0 is the signal that one side genuinely beats the other.

    Args:
        a: First series (e.g. engine points per roster-week).
        b: Second series, index-aligned with ``a`` (e.g. manager points).
        n_boot: Bootstrap resamples.
        alpha: Two-sided miss rate.
        seed: RNG seed.

    Returns:
        ``(low, high)`` for ``mean(a - b)``.

    Raises:
        ValueError: If the two series differ in length.
    """
    if len(a) != len(b):
        raise ValueError(f"paired series differ in length: {len(a)} vs {len(b)}")
    diffs = (np.asarray(a, dtype=float) - np.asarray(b, dtype=float)).tolist()
    return bootstrap_mean_ci(diffs, n_boot=n_boot, alpha=alpha, seed=seed)


def sign_test_pvalue(successes: int, n: int) -> float:
    """Two-sided exact binomial p-value that the success rate differs from 0.5.

    The honest test for "does the engine beat the manager more than half the time" on a
    small number of independent games. Exact (not a normal approximation), so it stays
    correct at the ~15-game season sample the H2H replay produces.

    Args:
        successes: Number of successes (e.g. weeks the engine won).
        n: Number of trials. ``0`` returns 1.0 (no evidence).

    Returns:
        The two-sided p-value in ``[0, 1]``.
    """
    if n <= 0:
        return 1.0
    successes = max(0, min(successes, n))
    observed = math.comb(n, successes) * 0.5**n
    # Two-sided: sum the probability of every outcome at least as extreme (as unlikely).
    total = 0.0
    for k in range(n + 1):
        p_k = math.comb(n, k) * 0.5**n
        if p_k <= observed + 1e-12:
            total += p_k
    return round(min(1.0, total), 4)
