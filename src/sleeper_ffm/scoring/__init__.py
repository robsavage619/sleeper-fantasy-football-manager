"""Scoring engine — the linchpin. Converts any stat line to fantasy points under league rules."""

from __future__ import annotations

from sleeper_ffm.scoring.engine import load_scoring, score, stats_from_nflverse

__all__ = ["load_scoring", "score", "stats_from_nflverse"]
