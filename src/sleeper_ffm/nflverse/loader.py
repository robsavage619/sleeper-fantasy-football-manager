"""nflverse data ingestion pipeline.

Pulls historical NFL stats from nflverse GitHub releases, writes parquet to
``data/nflverse/``, and exposes a single ``ingest(seasons)`` entry point.

Load order matters:
    1. ID crosswalk (``load_id_map``) — gsis_id ↔ sleeper_id join key; built and
       validated before anything else.
    2. Weekly box scores (``load_weekly``) — the scoring engine's primary input.
    3. Snap counts, NGS, rosters, schedules — supplementary signals.

All pulls are **idempotent**: existing parquet files are skipped unless ``force=True``.
Current-season data (latest year) is always refreshed.

URL note: nfl-data-py was archived 2025-09-25 and the old ``player_stats`` release
tag has no 2025 entry. For 2024+ we fetch directly from the ``stats_player`` release
tag, which uses a slightly different column schema (normalized on load). Older seasons
still come from ``nfl_data_py.import_weekly_data`` which targets the working legacy URLs.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import nfl_data_py as nfl
import polars as pl

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.config import NFLVERSE_DIR
from sleeper_ffm.net import retry_call

log = logging.getLogger(__name__)

# Stale-fallback registry: when a fresh fetch fails and we serve cached parquet instead,
# the affected source is recorded here so the freshness API and the briefing can surface
# it loudly (a silent stale read is the failure mode this exists to prevent). A successful
# refresh of the same source clears its entry.
_STALE_FALLBACKS: dict[str, str] = {}


def stale_fallbacks() -> dict[str, str]:
    """Return ``{source: reason}`` for every dataset currently served from a stale cache."""
    return dict(_STALE_FALLBACKS)


def clear_stale_fallbacks() -> None:
    """Reset the stale-fallback registry (e.g. at the start of a full refresh)."""
    _STALE_FALLBACKS.clear()


def _record_stale(source: str, detail: str) -> None:
    _STALE_FALLBACKS[source] = detail
    log.warning("stale fallback: %s — %s", source, detail)


def _clear_stale(source: str) -> None:
    _STALE_FALLBACKS.pop(source, None)


# Seasons available in nflverse. 2025 is the latest completed NFL season as of 2026-07.
_FIRST_SEASON = 2014
_CURRENT_SEASON = 2025

# nfl-data-py legacy URL (works for 2014-2024, dead for 2025+).
_WEEKLY_URL_LEGACY = (
    "https://github.com/nflverse/nflverse-data/releases/download/player_stats/"
    "player_stats_{season}.parquet"
)

# New stats_player release tag — per-year weekly parquet, 2024-present.
# Column schema differs from legacy; _normalize_stats_player() reconciles them.
_WEEKLY_URL_NEW = (
    "https://github.com/nflverse/nflverse-data/releases/download/stats_player/"
    "stats_player_week_{season}.parquet"
)

# First season where the new stats_player release tag is available.
_NEW_FORMAT_FIRST_SEASON = 2024

# Column renames needed to bring the new format into alignment with the legacy schema.
_NEW_FORMAT_RENAMES: dict[str, str] = {
    "passing_interceptions": "interceptions",
    "team": "recent_team",
}


def _normalize_stats_player(df: pl.DataFrame) -> pl.DataFrame:
    """Rename new-format columns to match the legacy nfl_data_py schema."""
    renames = {
        k: v for k, v in _NEW_FORMAT_RENAMES.items() if k in df.columns and v not in df.columns
    }
    if renames:
        df = df.rename(renames)
    return df


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

    # Completed seasons (<= _CURRENT_SEASON) are immutable — a cached parquet is a
    # true cache hit. Only future/in-progress seasons or force refetch from source.
    for yr in seasons:
        dest = _weekly_path(yr)
        if dest.exists() and not force and yr <= _CURRENT_SEASON:
            log.info("weekly/%d: cache hit", yr)
            frames.append(pl.read_parquet(dest))
        else:
            to_fetch.append(yr)

    for yr in to_fetch:
        dest = _weekly_path(yr)
        yr_df = _fetch_weekly_season(yr)
        if yr_df is None:
            if dest.exists():
                mtime = datetime.fromtimestamp(dest.stat().st_mtime, UTC).date().isoformat()
                _record_stale(
                    "nflverse_weekly", f"season {yr} fetch failed; serving cache from {mtime}"
                )
                frames.append(pl.read_parquet(dest))
            else:
                log.error("weekly/%d: fetch failed and no cache available; season dropped", yr)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_parquet(yr_df, dest)
        _clear_stale("nflverse_weekly")
        log.info("weekly/%d: %d rows written", yr, len(yr_df))
        frames.append(yr_df)

    if not frames:
        return _empty_weekly_frame()
    return _concat_across_schemas(frames)


def _weekly_path(season: int) -> Path:
    return NFLVERSE_DIR / "weekly" / f"{season}.parquet"


def _concat_across_schemas(frames: list[pl.DataFrame]) -> pl.DataFrame:
    """Concat per-season frames whose schemas may differ across nflverse eras.

    Seasons straddle nflverse schema boundaries — the legacy ``player_stats``
    format (<=2023) against ``stats_player`` (2024+), ``game_type`` renamed to
    ``season_type`` in the injury feed, depth charts dropping from 15 columns to
    12. ``diagonal_relaxed`` unions columns by name (null-filling what an era
    lacks) and supertypes shared columns, so a cross-era span concatenates
    instead of raising a ShapeError. Identical schemas take the plain path.

    Args:
        frames: One frame per season, in request order.

    Returns:
        The concatenated frame, or an empty frame when there is nothing to join.
    """
    if not frames:
        return pl.DataFrame()
    if len({tuple(f.columns) for f in frames}) == 1:
        return pl.concat(frames)
    return pl.concat(frames, how="diagonal_relaxed")


def _atomic_write_parquet(df: pl.DataFrame, dest: Path) -> None:
    """Write a parquet via a temp file + atomic rename to avoid torn reads."""
    tmp = dest.with_suffix(dest.suffix + f".tmp-{os.getpid()}")
    df.write_parquet(tmp)
    os.replace(tmp, dest)


def _fetch_weekly_season(year: int) -> pl.DataFrame | None:
    """Fetch one season's weekly data, trying the new stats_player format first for 2024+."""
    if year >= _NEW_FORMAT_FIRST_SEASON:
        url = _WEEKLY_URL_NEW.format(season=year)
        try:
            log.info("weekly/%d: fetching from stats_player release...", year)
            df = retry_call(
                lambda u=url: pl.read_parquet(u),
                exceptions=(Exception,),
                label=f"weekly/{year} stats_player",
            )
            df = _normalize_stats_player(df)
            log.info("weekly/%d: %d rows (new format)", year, len(df))
            return df
        except Exception as exc:
            log.warning("weekly/%d: stats_player URL failed (%s); using legacy", year, exc)

    try:
        log.info("weekly/%d: fetching via nfl_data_py...", year)
        df_raw = retry_call(
            lambda: nfl.import_weekly_data([year]),
            exceptions=(Exception,),
            label=f"weekly/{year} legacy",
        )
        df = cast(pl.DataFrame, pl.from_pandas(df_raw))
        log.info("weekly/%d: %d rows (legacy format)", year, len(df))
        return df
    except Exception as exc:
        log.warning("weekly/%d: unavailable from nflverse: %s", year, exc)
        return None


def weekly_source_url(season: int) -> str:
    """Return the preferred nflverse weekly parquet URL for a season."""
    if season >= _NEW_FORMAT_FIRST_SEASON:
        return _WEEKLY_URL_NEW.format(season=season)
    return _WEEKLY_URL_LEGACY.format(season=season)


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
        Season-aware, so the frame covers *at least* the requested seasons — callers
        that need exactly one season must filter on ``season`` themselves.
    """
    seasons = seasons or list(range(_FIRST_SEASON, _CURRENT_SEASON + 1))
    dest = NFLVERSE_DIR / "snaps.parquet"
    return _load_season_aware_single_file(dest, seasons, force, nfl.import_snap_counts)


def load_injuries(
    seasons: list[int] | None = None,
    force: bool = False,
) -> pl.DataFrame:
    """Load weekly injury reports from nflverse."""
    seasons = seasons or [_CURRENT_SEASON]
    frames: list[pl.DataFrame] = []
    for season in seasons:
        dest = NFLVERSE_DIR / "injuries" / f"{season}.parquet"
        if dest.exists() and not force:
            frames.append(pl.read_parquet(dest))
            continue
        try:
            df = cast(pl.DataFrame, pl.from_pandas(nfl.import_injuries([season])))
        except (HTTPError, URLError, OSError) as exc:
            log.warning("injuries/%d: unavailable from nflverse: %s", season, exc)
            if dest.exists():
                mtime = datetime.fromtimestamp(dest.stat().st_mtime, UTC).date().isoformat()
                _record_stale(
                    "nflverse_injuries",
                    f"season {season} fetch failed; serving cache from {mtime}",
                )
                frames.append(pl.read_parquet(dest))
            else:
                _record_stale(
                    "nflverse_injuries", f"season {season} fetch failed; no cache available"
                )
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(dest)
        _clear_stale("nflverse_injuries")
        frames.append(df)
    # Same schema drift as load_weekly: nflverse renamed game_type to season_type,
    # so a multi-season span raised a ShapeError that the callers caught and
    # reported as "injury history unavailable" while the parquet sat on disk.
    return _concat_across_schemas(frames)


# ---------------------------------------------------------------------------
# Next Gen Stats — tracking-derived separation, air yards, rush-yards-over-expected
# ---------------------------------------------------------------------------

# NGS is tracking-chip data; nflverse publishes it from 2016 on. Requesting an
# earlier season returns an empty frame rather than raising, so callers must clamp.
_NGS_FIRST_SEASON = 2016
_NGS_STAT_TYPES = ("receiving", "rushing", "passing")


def load_ngs(
    stat_type: str,
    seasons: list[int] | None = None,
    force: bool = False,
) -> pl.DataFrame:
    """Load Next Gen Stats tracking data for one stat type.

    NGS carries the separation, cushion, air-yards-share and yards-over-expected
    columns that box scores cannot express — the difference between a receiver
    who is open and one who is merely targeted.

    Rows with ``week == 0`` are NGS season aggregates, not a real week; they are
    preserved here and must be filtered by callers doing per-week work.

    Args:
        stat_type: One of ``receiving``, ``rushing``, ``passing``.
        seasons: Seasons to pull. Clamped to 2016+, the start of NGS coverage.
        force: Re-download, ignoring cache.

    Returns:
        Concatenated NGS DataFrame keyed by ``player_gsis_id``, ``season``, ``week``.

    Raises:
        ValueError: If ``stat_type`` is not a recognised NGS stat type.
    """
    if stat_type not in _NGS_STAT_TYPES:
        raise ValueError(f"stat_type must be one of {_NGS_STAT_TYPES}, got {stat_type!r}")

    seasons = seasons or list(range(_NGS_FIRST_SEASON, _CURRENT_SEASON + 1))
    wanted = [s for s in seasons if s >= _NGS_FIRST_SEASON]
    if skipped := sorted(set(seasons) - set(wanted)):
        log.info("ngs/%s: seasons %s predate NGS coverage; skipped", stat_type, skipped)

    source = f"nflverse_ngs_{stat_type}"
    frames: list[pl.DataFrame] = []
    for season in wanted:
        dest = NFLVERSE_DIR / "ngs" / stat_type / f"{season}.parquet"
        if dest.exists() and not force and season <= _CURRENT_SEASON:
            frames.append(pl.read_parquet(dest))
            continue
        try:
            df = cast(
                pl.DataFrame,
                pl.from_pandas(
                    retry_call(
                        lambda st=stat_type, s=season: nfl.import_ngs_data(st, [s]),
                        exceptions=(Exception,),
                        label=f"ngs/{stat_type}/{season}",
                    )
                ),
            )
        except Exception as exc:
            log.warning("ngs/%s/%d: unavailable from nflverse: %s", stat_type, season, exc)
            if dest.exists():
                mtime = datetime.fromtimestamp(dest.stat().st_mtime, UTC).date().isoformat()
                _record_stale(source, f"season {season} fetch failed; serving cache from {mtime}")
                frames.append(pl.read_parquet(dest))
            else:
                _record_stale(source, f"season {season} fetch failed; no cache available")
            continue
        if df.is_empty():
            log.warning("ngs/%s/%d: source returned no rows", stat_type, season)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_parquet(df, dest)
        _clear_stale(source)
        log.info("ngs/%s/%d: %d rows written", stat_type, season, len(df))
        frames.append(df)

    if not frames:
        return pl.DataFrame()
    if len({tuple(f.columns) for f in frames}) == 1:
        return pl.concat(frames)
    return pl.concat(frames, how="diagonal_relaxed")


# ---------------------------------------------------------------------------
# Pro Football Reference advanced stats — charted drops, broken tackles, pressure
# ---------------------------------------------------------------------------

# PFR advanced splits start in 2018 and are keyed by pfr_player_id, which the
# id_map crosswalk resolves back to gsis_id.
_PFR_FIRST_SEASON = 2018
_PFR_STAT_TYPES = ("pass", "rec", "rush", "def")


def load_pfr_advanced(
    stat_type: str,
    seasons: list[int] | None = None,
    force: bool = False,
) -> pl.DataFrame:
    """Load weekly Pro Football Reference advanced stats for one stat type.

    Supplies charted detail the box score omits — drops, broken tackles, and
    yards after contact — keyed by ``pfr_player_id``.

    Args:
        stat_type: One of ``pass``, ``rec``, ``rush``, ``def``.
        seasons: Seasons to pull. Clamped to 2018+, the start of PFR coverage.
        force: Re-download, ignoring cache.

    Returns:
        Concatenated weekly PFR DataFrame.

    Raises:
        ValueError: If ``stat_type`` is not a recognised PFR stat type.
    """
    if stat_type not in _PFR_STAT_TYPES:
        raise ValueError(f"stat_type must be one of {_PFR_STAT_TYPES}, got {stat_type!r}")

    seasons = seasons or list(range(_PFR_FIRST_SEASON, _CURRENT_SEASON + 1))
    wanted = [s for s in seasons if s >= _PFR_FIRST_SEASON]
    if skipped := sorted(set(seasons) - set(wanted)):
        log.info("pfr/%s: seasons %s predate PFR coverage; skipped", stat_type, skipped)

    source = f"nflverse_pfr_{stat_type}"
    frames: list[pl.DataFrame] = []
    for season in wanted:
        dest = NFLVERSE_DIR / "pfr" / stat_type / f"{season}.parquet"
        if dest.exists() and not force and season <= _CURRENT_SEASON:
            frames.append(pl.read_parquet(dest))
            continue
        try:
            df = cast(
                pl.DataFrame,
                pl.from_pandas(
                    retry_call(
                        lambda st=stat_type, s=season: nfl.import_weekly_pfr(st, [s]),
                        exceptions=(Exception,),
                        label=f"pfr/{stat_type}/{season}",
                    )
                ),
            )
        except Exception as exc:
            log.warning("pfr/%s/%d: unavailable from nflverse: %s", stat_type, season, exc)
            if dest.exists():
                mtime = datetime.fromtimestamp(dest.stat().st_mtime, UTC).date().isoformat()
                _record_stale(source, f"season {season} fetch failed; serving cache from {mtime}")
                frames.append(pl.read_parquet(dest))
            else:
                _record_stale(source, f"season {season} fetch failed; no cache available")
            continue
        if df.is_empty():
            log.warning("pfr/%s/%d: source returned no rows", stat_type, season)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_parquet(df, dest)
        _clear_stale(source)
        log.info("pfr/%s/%d: %d rows written", stat_type, season, len(df))
        frames.append(df)

    if not frames:
        return pl.DataFrame()
    if len({tuple(f.columns) for f in frames}) == 1:
        return pl.concat(frames)
    return pl.concat(frames, how="diagonal_relaxed")


_PBP_COLUMNS = [
    "season",
    "week",
    "game_id",
    "season_type",
    "posteam",
    "defteam",
    "play_type",
    "pass",
    "rush",
    "complete_pass",
    "receiver_player_id",
    "rusher_player_id",
    "passer_player_id",
    "yardline_100",
    "touchdown",
    "pass_touchdown",
    "rush_touchdown",
    "air_yards",
    "yards_gained",
    "epa",
]


def load_pbp(
    seasons: list[int] | None = None,
    force: bool = False,
) -> pl.DataFrame:
    """Load play-by-play data, trimmed to the columns yard-line/xFP calibration needs.

    Full nflverse PBP carries 370+ columns (participation, formations, NGS charting);
    fetching only :data:`_PBP_COLUMNS` and skipping the participation merge
    (``include_participation=False``) keeps each season's pull to ~20 columns instead
    of downloading and caching data nothing here reads.
    """
    seasons = seasons or [_CURRENT_SEASON]
    frames: list[pl.DataFrame] = []
    for season in seasons:
        dest = NFLVERSE_DIR / "pbp" / f"{season}.parquet"
        if dest.exists() and not force:
            frames.append(pl.read_parquet(dest))
            continue
        try:
            df_raw = nfl.import_pbp_data(
                [season], columns=_PBP_COLUMNS, include_participation=False, downcast=True
            )
            df = cast(pl.DataFrame, pl.from_pandas(df_raw))
        except (HTTPError, URLError, OSError, ValueError) as exc:
            log.warning("pbp/%d: unavailable from nflverse: %s", season, exc)
            if dest.exists():
                mtime = datetime.fromtimestamp(dest.stat().st_mtime, UTC).date().isoformat()
                _record_stale(
                    "nflverse_pbp", f"season {season} fetch failed; serving cache from {mtime}"
                )
                frames.append(pl.read_parquet(dest))
            else:
                _record_stale("nflverse_pbp", f"season {season} fetch failed; no cache available")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(dest)
        _clear_stale("nflverse_pbp")
        frames.append(df)
    return pl.concat(frames) if frames else pl.DataFrame()


def load_depth_charts(
    seasons: list[int] | None = None,
    force: bool = False,
) -> pl.DataFrame:
    """Load weekly depth charts from nflverse."""
    seasons = seasons or [_CURRENT_SEASON]
    frames: list[pl.DataFrame] = []
    for season in seasons:
        dest = NFLVERSE_DIR / "depth_charts" / f"{season}.parquet"
        if dest.exists() and not force:
            frames.append(pl.read_parquet(dest))
            continue
        try:
            df = cast(pl.DataFrame, pl.from_pandas(nfl.import_depth_charts([season])))
        except (HTTPError, URLError, OSError) as exc:
            log.warning("depth_charts/%d: unavailable from nflverse: %s", season, exc)
            if dest.exists():
                mtime = datetime.fromtimestamp(dest.stat().st_mtime, UTC).date().isoformat()
                _record_stale(
                    "nflverse_depth_charts",
                    f"season {season} fetch failed; serving cache from {mtime}",
                )
                frames.append(pl.read_parquet(dest))
            else:
                _record_stale(
                    "nflverse_depth_charts", f"season {season} fetch failed; no cache available"
                )
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(dest)
        _clear_stale("nflverse_depth_charts")
        frames.append(df)

    # nflverse replaced the weekly depth-chart feed with a timestamped one. It is
    # still a time series (hundreds of captures across a season), just keyed on a
    # capture time rather than season/week, with every column consumers read
    # renamed. Normalise it onto the legacy schema rather than dropping it.
    normalised = [_normalize_depth_snapshot(f) for f in frames]
    usable = [f for f in normalised if not f.is_empty()]
    if dropped := len(normalised) - len(usable):
        _record_stale(
            "nflverse_depth_charts",
            f"{dropped} season(s) could not be normalised onto the weekly depth schema "
            "and were excluded; depth history is incomplete",
        )
        log.warning("depth_charts: excluded %d unnormalisable frame(s)", dropped)
    return _concat_across_schemas(usable)


# New-format depth chart column -> legacy name. pos_rank is the player's order at
# his position, which is exactly what the legacy depth_team string encoded.
_DEPTH_SNAPSHOT_RENAMES = {
    "team": "club_code",
    "player_name": "full_name",
    "pos_abb": "depth_position",
    "pos_rank": "depth_team",
}


def _normalize_depth_snapshot(df: pl.DataFrame) -> pl.DataFrame:
    """Map nflverse's timestamped depth-chart format onto the legacy weekly schema.

    The new feed drops ``season``/``week`` for a ``dt`` capture timestamp and
    renames the columns every caller reads. Season and week are recovered by
    locating each capture in the NFL schedule, so the result sorts and filters
    exactly like the older per-week rows.

    Args:
        df: One season's depth-chart frame, either format.

    Returns:
        The frame in legacy shape. Already-legacy frames pass through untouched;
        a frame in neither shape comes back empty so the caller can flag it.
    """
    if "season" in df.columns and "week" in df.columns:
        return df
    if "dt" not in df.columns:
        return pl.DataFrame()

    out = df.rename({k: v for k, v in _DEPTH_SNAPSHOT_RENAMES.items() if k in df.columns})
    if "depth_team" in out.columns:
        out = out.with_columns(pl.col("depth_team").cast(pl.Utf8))
    if "depth_position" in out.columns and "position" not in out.columns:
        out = out.with_columns(pl.col("depth_position").alias("position"))

    captured = pl.col("dt").str.slice(0, 10).str.to_date(strict=False)
    out = out.with_columns(captured.alias("_captured_on")).drop_nulls("_captured_on")
    if out.is_empty():
        return pl.DataFrame()

    weeks = _schedule_week_index()
    if weeks.is_empty():
        # Without the schedule there is no honest week to assign, and inventing
        # one would corrupt the ordering every consumer relies on.
        log.warning("depth_charts: schedule unavailable; cannot date the snapshot feed")
        return pl.DataFrame()

    # Each capture belongs to the most recent week that had already kicked off.
    out = (
        out.sort("_captured_on")
        .join_asof(weeks.sort("_week_start"), left_on="_captured_on", right_on="_week_start")
        .drop_nulls(["season", "week"])
    )
    if out.is_empty():
        return pl.DataFrame()

    # The new feed captures several times a week; the legacy schema this maps onto
    # is one row per player per week. Without collapsing to the last capture in
    # each week, consumers that take "the latest depth chart" get several
    # overlapping ones stacked together and read a player as his own backup.
    key = [c for c in ("season", "week", "club_code", "gsis_id", "full_name") if c in out.columns]
    if key:
        out = out.sort("dt").unique(subset=key, keep="last", maintain_order=True)
    return out.drop(["_captured_on", "_week_start"])


@ttl_cache(key=lambda: "depth_week_index")
def _schedule_week_index() -> pl.DataFrame:
    """First kickoff date of every NFL week, for dating the depth-chart feed."""
    try:
        schedules = load_schedules()
    except Exception as exc:
        log.warning("depth_charts: schedule load failed: %s", exc)
        return pl.DataFrame()
    needed = {"season", "week", "gameday"}
    if schedules.is_empty() or not needed.issubset(schedules.columns):
        return pl.DataFrame()
    return (
        schedules.select(["season", "week", "gameday"])
        .with_columns(pl.col("gameday").str.to_date(strict=False).alias("_week_start"))
        .drop_nulls("_week_start")
        .group_by(["season", "week"])
        .agg(pl.col("_week_start").min())
        .sort("_week_start")
    )


# ---------------------------------------------------------------------------
# Seasonal aggregates — season-level totals (faster than weekly for age curves)
# ---------------------------------------------------------------------------


# nfl_data_py's import_seasonal_data reads the legacy player_stats_{year} release,
# which nflverse stopped publishing after 2024 (2025 is a hard 404). Requesting it
# raises rather than returning empty, so callers must clamp like load_ngs does.
_SEASONAL_LAST_SEASON = 2024


def load_seasonal(
    seasons: list[int] | None = None,
    force: bool = False,
) -> pl.DataFrame:
    """Load per-player seasonal totals.

    Args:
        seasons: Seasons to pull (default: ``_FIRST_SEASON`` - ``_SEASONAL_LAST_SEASON``).
        force: Re-download all, ignoring cache.

    Returns:
        Seasonal stats DataFrame covering at least the requested seasons that fall
        within nflverse's legacy-format coverage. Seasons past
        ``_SEASONAL_LAST_SEASON`` are skipped; use ``load_weekly`` for those.
    """
    seasons = seasons or list(range(_FIRST_SEASON, _SEASONAL_LAST_SEASON + 1))
    wanted = [s for s in seasons if s <= _SEASONAL_LAST_SEASON]
    if skipped := sorted(set(seasons) - set(wanted)):
        log.info("seasonal: seasons %s postdate legacy player_stats coverage; skipped", skipped)
    if not wanted:
        return pl.DataFrame()

    dest = NFLVERSE_DIR / "seasonal.parquet"
    return _load_season_aware_single_file(dest, wanted, force, nfl.import_seasonal_data)


# ---------------------------------------------------------------------------
# Schedules + rosters — SoS and depth context
# ---------------------------------------------------------------------------


def _load_season_aware_single_file(
    dest: Path,
    seasons: list[int],
    force: bool,
    fetch: Any,
) -> pl.DataFrame:
    """Load a single-file (not per-season) nflverse dataset, filling missing seasons.

    Unlike ``load_weekly``/``load_injuries`` (one parquet per season), schedules and
    rosters are cached in one shared file. A naive "return cache if it exists" check
    silently pins that file to whichever seasons were requested by the first caller
    — later callers asking for other seasons get nothing for them. This fetches only
    the seasons missing from the cache and merges them in. Freshness for the current,
    in-progress season is driven by an explicit ``force=True`` call (the admin refresh
    job), same convention as ``load_weekly``.

    Args:
        dest: Shared parquet path.
        seasons: Seasons the caller wants present.
        force: Re-download everything, ignoring cache.
        fetch: ``list[int] -> pandas.DataFrame`` fetch function (e.g. ``nfl.import_schedules``).

    Returns:
        DataFrame covering at least the requested seasons.
    """
    cached = pl.read_parquet(dest) if dest.exists() and not force else None
    cached_seasons: set[int] = (
        set(cached["season"].unique().to_list())
        if cached is not None and "season" in cached.columns
        else set()
    )

    missing = sorted(set(seasons) - cached_seasons)
    if cached is not None and not force and not missing:
        return cached

    fetch_seasons = sorted(set(seasons)) if force else missing
    log.info("%s: fetching seasons %s...", dest.stem, fetch_seasons)
    fresh = cast(pl.DataFrame, pl.from_pandas(fetch(fetch_seasons)))

    if cached is not None and not force:
        keep = cached.filter(~pl.col("season").is_in(fetch_seasons))
        merged = pl.concat([keep, fresh], how="diagonal_relaxed") if not keep.is_empty() else fresh
    else:
        merged = fresh

    dest.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_parquet(merged, dest)
    return merged


def load_schedules(
    seasons: list[int] | None = None,
    force: bool = False,
) -> pl.DataFrame:
    """Load NFL game schedules (spread/total lines, weather, venue).

    Season-aware: a season missing from the cache is fetched and merged in rather
    than silently omitted. The current season is always refreshed to pick up
    updated odds/results as the week progresses.
    """
    seasons = seasons or list(range(_FIRST_SEASON, _CURRENT_SEASON + 1))
    dest = NFLVERSE_DIR / "schedules.parquet"
    return _load_season_aware_single_file(dest, seasons, force, nfl.import_schedules)


def load_rosters(
    seasons: list[int] | None = None,
    force: bool = False,
) -> pl.DataFrame:
    """Load weekly roster snapshots (depth/injury/team context).

    Season-aware: a season missing from the cache is fetched and merged in rather
    than silently omitted.
    """
    seasons = seasons or list(range(_FIRST_SEASON, _CURRENT_SEASON + 1))
    dest = NFLVERSE_DIR / "rosters.parquet"
    return _load_season_aware_single_file(dest, seasons, force, nfl.import_weekly_rosters)


# ---------------------------------------------------------------------------
# Full backfill — call once to seed the data directory
# ---------------------------------------------------------------------------


def ingest(
    seasons: list[int] | None = None,
    force: bool = False,
    skip_snaps: bool = False,
    skip_rosters: bool = False,
    skip_status: bool = False,
    skip_advanced: bool = False,
) -> None:
    """Run the full nflverse ingestion pipeline.

    Order: id_map → weekly → seasonal → [snaps] → schedules → [rosters] →
    [status feeds] → [advanced tracking].

    Args:
        seasons: Seasons to ingest (default: full historical range).
        force: Re-fetch everything, ignoring cached parquet.
        skip_snaps: Skip snap-count download (saves ~30s, optional signal).
        skip_rosters: Skip roster snapshot download (saves ~60s).
        skip_status: Skip the in-season status feeds — injuries, depth charts, and
            play-by-play. These previously loaded lazily on first model access and were
            never force-refreshed by ingest; pulling them here closes that coverage hole.
        skip_advanced: Skip Next Gen Stats and PFR advanced splits. These back the
            research studies rather than the live surfaces, so a routine in-season
            refresh does not need them.
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
    if not skip_status:
        status_seasons = _status_seasons(seasons)
        load_injuries(seasons=status_seasons, force=force)
        load_depth_charts(seasons=status_seasons, force=force)
        load_pbp(seasons=status_seasons, force=force)
    if not skip_advanced:
        for ngs_type in _NGS_STAT_TYPES:
            load_ngs(ngs_type, seasons=seasons, force=force)
        for pfr_type in ("rec", "rush", "pass"):
            load_pfr_advanced(pfr_type, seasons=seasons, force=force)
    log.info("=== nflverse ingest complete ===")


def _status_seasons(seasons: list[int] | None) -> list[int]:
    """Seasons to pull status feeds for — injuries/depth/PBP only publish from 2024 on.

    Restricts a broad ``--full`` request (2014-2025) to the range these feeds actually
    cover, so a backfill doesn't spend retries on seasons nflverse never served them for.
    """
    requested = seasons or [_CURRENT_SEASON]
    covered = [s for s in requested if s >= _NEW_FORMAT_FIRST_SEASON]
    return covered or [_CURRENT_SEASON]
