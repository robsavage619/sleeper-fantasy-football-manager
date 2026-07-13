"""Project-wide configuration and paths.

League-specific facts are verified live from Sleeper (see ``data/league_settings.json``),
never hardcoded into logic. Constants here are stable identifiers and filesystem layout.
"""

from __future__ import annotations

from pathlib import Path

# This league (verified 2026-07-12): "The League", 2026, dynasty, PPR, 10 teams.
CURRENT_LEAGUE_YEAR = 2026
LATEST_COMPLETED_NFL_SEASON = 2025
LEAGUE_ID = "1335321166146990080"
DRAFT_ID = "1335321166155358208"  # annual rookie/offseason draft (4 rounds, linear)
MY_USER_ID = "507751121488523264"  # robsavage on Sleeper
MY_ROSTER_ID = 2  # Rob's roster in this league
SLEEPER_BASE = "https://api.sleeper.app/v1"

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
NFLVERSE_DIR = DATA_DIR / "nflverse"

# Vault research corpus (built from scratch for this product).
VAULT_DIR = Path.home() / "Vault" / "savage_vault"

for _d in (DATA_DIR, CACHE_DIR, NFLVERSE_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def cached_weekly_seasons() -> list[int]:
    """Return cached nflverse weekly seasons available on disk."""
    return sorted(
        int(path.stem)
        for path in (NFLVERSE_DIR / "weekly").glob("*.parquet")
        if path.stem.isdigit()
    )


def _latest_cached_weekly_season() -> int | None:
    cached_seasons = cached_weekly_seasons()
    return max(cached_seasons) if cached_seasons else None


PREFERRED_VALUE_SEASON = LATEST_COMPLETED_NFL_SEASON
# Always target the preferred season. If the parquet is missing, the loader will
# error loudly rather than silently falling back to stale data.
DEFAULT_VALUE_SEASON = PREFERRED_VALUE_SEASON


def _warn_if_stale() -> None:
    import warnings

    cached = cached_weekly_seasons()
    if PREFERRED_VALUE_SEASON not in cached:
        warnings.warn(
            f"Preferred value season {PREFERRED_VALUE_SEASON} not cached "
            f"(cached: {cached}). Run 'sffm ingest' to fetch data. "
            "Valuation will fail or fall back to stale data until resolved.",
            stacklevel=2,
        )


_warn_if_stale()
