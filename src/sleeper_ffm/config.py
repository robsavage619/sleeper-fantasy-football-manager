"""Project-wide configuration and paths.

League-specific facts are verified live from Sleeper (see ``data/league_settings.json``),
never hardcoded into logic. Constants here are stable identifiers and filesystem layout.
"""

from __future__ import annotations

from pathlib import Path

# This league (verified 2026-07-12): "The League", 2026, dynasty, PPR, 10 teams.
LEAGUE_ID = "1335321166146990080"
DRAFT_ID = "1335321166155358208"  # annual rookie/offseason draft (4 rounds, linear)
MY_USER_ID = "507751121488523264"  # robsavage on Sleeper
MY_ROSTER_ID = 2                   # Rob's roster in this league
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
