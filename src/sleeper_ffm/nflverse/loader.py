"""nflverse data ingestion pipeline.

Pulls historical NFL stats from ``nfl-data-py`` (nflverse), writes parquet to
``data/nflverse/``, and exposes a single ``ingest(seasons)`` entry point.

Load order matters:
    1. ID crosswalk (``load_id_map``) — gsis_id ↔ sleeper_id join key; built and
       validated before anything else.
    2. Weekly box scores (``load_weekly``) — the scoring engine's primary input.
    3. Snap counts, NGS, rosters, schedules — supplementary signals.

All pulls are **idempotent**: existing parquet files are skipped unless ``force=True``.
Current-season data (latest year) is always refreshed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import nfl_data_py as nfl
import polars as pl

from sleeper_ffm.config import NFLVERSE_DIR

log = logging.getLogger(__name__)

# Seasons available in nflverse. 2025 is the latest completed NFL season as of 2026-07.
_FIRST_SEASON = 2014
_CURRENT_SEASON = 2025
_WEEKLY_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/player_stats/"
    "player_stats_{season}.parquet"
)


# ---------------------------------------------------------------------------
# ID crosswalk — the join key between Sleeper player IDs and nflverse stats
# ---------------------------------------------------------------------------


def load_id_map(force: bool = False) -> pl.DataFrame:
    """Load the nflverse player ID crosswalk (gsis_id ↔ sleeper_id ↔ pfr/espn).

    Args:
        force: Re-download even if cache exists.

    Returns:
        DataFrame with columns including ``gsis_id``, ``sleeper_id``, ``espn_id``,
        ``pfr_id``, ``name``, ``position``, ``team``.
    """
    dest = NFLVERSE_DIR / "id_map.parquet"
    if dest.exists() and not force:
        log.info("id_map: loading from cache %s", dest)
        return pl.read_parquet(dest)

    log.info("id_map: downloading from nflverse...")
    df_raw = nfl.import_ids()
    df = cast(pl.DataFrame, pl.from_pandas(df_raw))
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(dest)
    log.info("id_map: %d rows written to %s", len(df), dest)
    return df


# ---------------------------------------------------------------------------
# Weekly box scores — core scoring engine input
# ---------------------------------------------------------------------------


def load_weekly(
    seasons: list[int] | None = None,
    force: bool = False,
) -> pl.DataFrame:
    """Load per-player weekly box scores from nflverse.

    Args:
        seasons: Seasons to pull. Defaults to ``_FIRST_SEASON`` - ``_CURRENT_SEASON``.
            Current season is always refreshed.
        force: Re-download all seasons, ignoring cache.

    Returns:
        Concatenated weekly stats DataFrame (all seasons, regular season + playoffs).
    """
    seasons = seasons or list(range(_FIRST_SEASON, _CURRENT_SEASON + 1))
    frames: list[pl.DataFrame] = []
    to_fetch: list[int] = []

    for yr in seasons:
        dest = _weekly_path(yr)
        if dest.exists() and not force and yr < _CURRENT_SEASON:
            log.info("weekly/%d: cache hit", yr)
            frames.append(pl.read_parquet(dest))
        else:
            to_fetch.append(yr)

    for yr in to_fetch:
        try:
            log.info("weekly/%d: fetching...", yr)
            df_raw = nfl.import_weekly_data([yr])
            yr_df = cast(pl.DataFrame, pl.from_pandas(df_raw))
            dest = _weekly_path(yr)
            dest.parent.mkdir(parents=True, exist_ok=True)
            yr_df.write_parquet(dest)
            log.info("weekly/%d: %d rows written", yr, len(yr_df))
            frames.append(yr_df)
        except (HTTPError, URLError, OSError) as exc:
            log.warning("weekly/%d: unavailable from nflverse: %s", yr, exc)

    if not frames:
        return _empty_weekly_frame()
    return pl.concat(frames)


def _weekly_path(season: int) -> Path:
    return NFLVERSE_DIR / "weekly" / f"{season}.parquet"


def weekly_source_url(season: int) -> str:
    """Return the nflverse weekly parquet URL for a season."""
    return _WEEKLY_URL.format(season=season)


def weekly_source_available(season: int, timeout: float = 3.0) -> bool:
    """Check whether nflverse currently publishes weekly player stats for a season."""
    request = Request(weekly_source_url(season), method="HEAD")
    try:
        with urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 400
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def _empty_weekly_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "season": pl.Int64,
            "week": pl.Int64,
            "season_type": pl.Utf8,
            "player_id": pl.Utf8,
            "position": pl.Utf8,
            "player_display_name": pl.Utf8,
            "recent_team": pl.Utf8,
        }
    )


# ---------------------------------------------------------------------------
# Snap counts — opportunity/trend signal
# ---------------------------------------------------------------------------


def load_snaps(
    seasons: list[int] | None = None,
    force: bool = False,
) -> pl.DataFrame:
    """Load per-player per-game snap counts.

    Args:
        seasons: Seasons to pull (default: ``_FIRST_SEASON`` - ``_CURRENT_SEASON``).
        force: Re-download all, ignoring cache.

    Returns:
        Snap count DataFrame with ``player_id``, ``season``, ``week``, ``offense_snaps``, etc.
    """
    seasons = seasons or list(range(_FIRST_SEASON, _CURRENT_SEASON + 1))
    dest = NFLVERSE_DIR / "snaps.parquet"
    if dest.exists() and not force:
        log.info("snaps: loading from cache")
        return pl.read_parquet(dest)

    log.info("snaps: fetching seasons %s...", seasons)
    df_raw = nfl.import_snap_counts(seasons)
    df = cast(pl.DataFrame, pl.from_pandas(df_raw))
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(dest)
    log.info("snaps: %d rows written", len(df))
    return df


# ---------------------------------------------------------------------------
# Seasonal aggregates — season-level totals (faster than weekly for age curves)
# ---------------------------------------------------------------------------


def load_seasonal(
    seasons: list[int] | None = None,
    force: bool = False,
) -> pl.DataFrame:
    """Load per-player seasonal totals.

    Args:
        seasons: Seasons to pull (default: ``_FIRST_SEASON`` - ``_CURRENT_SEASON``).
        force: Re-download all, ignoring cache.

    Returns:
        Seasonal stats DataFrame.
    """
    seasons = seasons or list(range(_FIRST_SEASON, _CURRENT_SEASON + 1))
    dest = NFLVERSE_DIR / "seasonal.parquet"
    if dest.exists() and not force:
        log.info("seasonal: loading from cache")
        return pl.read_parquet(dest)

    log.info("seasonal: fetching seasons %s...", seasons)
    df_raw = nfl.import_seasonal_data(seasons)
    df = cast(pl.DataFrame, pl.from_pandas(df_raw))
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(dest)
    log.info("seasonal: %d rows written", len(df))
    return df


# ---------------------------------------------------------------------------
# Schedules + rosters — SoS and depth context
# ---------------------------------------------------------------------------


def load_schedules(
    seasons: list[int] | None = None,
    force: bool = False,
) -> pl.DataFrame:
    """Load NFL game schedules."""
    seasons = seasons or list(range(_FIRST_SEASON, _CURRENT_SEASON + 1))
    dest = NFLVERSE_DIR / "schedules.parquet"
    if dest.exists() and not force:
        return pl.read_parquet(dest)
    df = cast(pl.DataFrame, pl.from_pandas(nfl.import_schedules(seasons)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(dest)
    return df


def load_rosters(
    seasons: list[int] | None = None,
    force: bool = False,
) -> pl.DataFrame:
    """Load weekly roster snapshots (depth/injury/team context)."""
    seasons = seasons or list(range(_FIRST_SEASON, _CURRENT_SEASON + 1))
    dest = NFLVERSE_DIR / "rosters.parquet"
    if dest.exists() and not force:
        return pl.read_parquet(dest)
    df = cast(pl.DataFrame, pl.from_pandas(nfl.import_weekly_rosters(seasons)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(dest)
    return df


# ---------------------------------------------------------------------------
# Full backfill — call once to seed the data directory
# ---------------------------------------------------------------------------


def ingest(
    seasons: list[int] | None = None,
    force: bool = False,
    skip_snaps: bool = False,
    skip_rosters: bool = False,
) -> None:
    """Run the full nflverse ingestion pipeline.

    Order: id_map → weekly → seasonal → [snaps] → [schedules + rosters].

    Args:
        seasons: Seasons to ingest (default: full historical range).
        force: Re-fetch everything, ignoring cached parquet.
        skip_snaps: Skip snap-count download (saves ~30s, optional signal).
        skip_rosters: Skip roster snapshot download (saves ~60s).
    """
    log.info("=== nflverse ingest start ===")
    load_id_map(force=force)
    load_weekly(seasons=seasons, force=force)
    load_seasonal(seasons=seasons, force=force)
    if not skip_snaps:
        load_snaps(seasons=seasons, force=force)
    load_schedules(seasons=seasons, force=force)
    if not skip_rosters:
        load_rosters(seasons=seasons, force=force)
    log.info("=== nflverse ingest complete ===")
