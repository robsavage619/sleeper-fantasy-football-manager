"""Research studies — empirical work behind the engine's priors.

Modules here answer questions rather than serve surfaces: they read cached
parquet, compute effects under this league's scoring, and report findings the
engine only adopts once they survive an out-of-sample backtest.
"""

from __future__ import annotations
