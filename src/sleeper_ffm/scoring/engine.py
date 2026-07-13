"""Scoring engine: stat line -> fantasy points under this league's exact rules.

Every valuation, projection, and historical read flows through :func:`score`. The engine is
driven by the league's ``scoring_settings`` (loaded from ``data/league_settings.json``), never
by hardcoded weights, so it stays correct if the commissioner changes settings.

Two input shapes are supported:
- **Sleeper stat dicts** (keys already in Sleeper's vocabulary, e.g. ``rec``, ``rush_yd``).
- **nflverse weekly rows** via :func:`stats_from_nflverse`, which maps columns to Sleeper keys.

Threshold bonuses (100/200-yd, 300/400 pass-yd, 25-completion, 20-carry) are derived here.
Length-based TD bonuses (``*_td_40p``) require per-play data and are read from the input when
present (Sleeper provides them); the nflverse aggregate path leaves them at 0 — a documented,
small under-credit for 40+ yard TDs, corrected once play-by-play is wired.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping

from sleeper_ffm.config import DATA_DIR

log = logging.getLogger(__name__)

# nflverse weekly column -> Sleeper stat key (linear, 1:1). Fumbles handled separately.
_NFLVERSE_TO_SLEEPER: dict[str, str] = {
    "completions": "pass_cmp",
    "attempts": "pass_att",
    "passing_yards": "pass_yd",
    "passing_tds": "pass_td",
    "interceptions": "pass_int",
    "passing_2pt_conversions": "pass_2pt",
    "carries": "rush_att",
    "rushing_yards": "rush_yd",
    "rushing_tds": "rush_td",
    "rushing_2pt_conversions": "rush_2pt",
    "receptions": "rec",
    "targets": "rec_tgt",
    "receiving_yards": "rec_yd",
    "receiving_tds": "rec_td",
    "receiving_2pt_conversions": "rec_2pt",
}
_FUMBLE_LOST_COLS = ("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost")


def load_scoring(path: str | None = None) -> dict[str, float]:
    """Load the league scoring settings.

    Args:
        path: Optional override path to a league-settings JSON. Defaults to the cached snapshot.

    Returns:
        The ``scoring_settings`` mapping of stat key to points-per-unit.
    """
    settings_path = path or str(DATA_DIR / "league_settings.json")
    with open(settings_path) as fh:
        return json.load(fh)["scoring_settings"]


def stats_from_nflverse(row: Mapping[str, object]) -> dict[str, float]:
    """Convert an nflverse weekly row to a Sleeper-keyed stat dict (bonuses derived).

    Args:
        row: One player-week record from ``nfl_data_py.import_weekly_data``.

    Returns:
        Stat dict keyed by Sleeper stat names, ready for :func:`score`.
    """
    stats: dict[str, float] = {}
    for col, key in _NFLVERSE_TO_SLEEPER.items():
        val = row.get(col)
        if val is not None and not _is_nan(val):
            stats[key] = stats.get(key, 0.0) + float(val)

    fum_lost = sum(
        float(row[c]) for c in _FUMBLE_LOST_COLS if row.get(c) is not None and not _is_nan(row[c])
    )
    if fum_lost:
        stats["fum_lost"] = fum_lost

    _derive_bonuses(stats)
    return stats


def score(stats: Mapping[str, float], scoring: Mapping[str, float]) -> float:
    """Score a stat line under the given scoring settings.

    Args:
        stats: Stat dict in Sleeper's vocabulary. Threshold bonuses are derived if absent.
        scoring: The league ``scoring_settings`` (see :func:`load_scoring`).

    Returns:
        Fantasy points, rounded to 2 decimals.
    """
    stats = dict(stats)
    _derive_bonuses(stats)

    total = 0.0
    for key, weight in scoring.items():
        if not weight:
            continue
        val = stats.get(key)
        if val:
            total += weight * float(val)
    return round(total, 2)


def _derive_bonuses(stats: dict[str, float]) -> None:
    """Add threshold-bonus flag keys to ``stats`` in place (idempotent)."""
    _step(stats, "bonus_rec_yd_100", stats.get("rec_yd", 0.0) >= 100)
    _step(stats, "bonus_rec_yd_200", stats.get("rec_yd", 0.0) >= 200)
    _step(stats, "bonus_rush_yd_100", stats.get("rush_yd", 0.0) >= 100)
    _step(stats, "bonus_rush_yd_200", stats.get("rush_yd", 0.0) >= 200)
    _step(stats, "bonus_pass_yd_300", stats.get("pass_yd", 0.0) >= 300)
    _step(stats, "bonus_pass_yd_400", stats.get("pass_yd", 0.0) >= 400)
    _step(stats, "bonus_pass_cmp_25", stats.get("pass_cmp", 0.0) >= 25)
    _step(stats, "bonus_rush_att_20", stats.get("rush_att", 0.0) >= 20)


def _step(stats: dict[str, float], key: str, fires: bool) -> None:
    """Set a step-bonus flag to 1.0 when it fires, unless already supplied by the source."""
    if key not in stats:
        stats[key] = 1.0 if fires else 0.0


def _is_nan(val: object) -> bool:
    return isinstance(val, float) and val != val
