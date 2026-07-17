"""Keyless college production history from sportsdataverse ESPN box scores.

Unlike CFBD (which needs an API key), sportsdataverse publishes per-game ESPN
box-score parquet files on GitHub over plain HTTPS — no auth. We download a
season once (~1 MB), cache it, and aggregate a named player's games into
season totals for receiving / rushing / passing.

Data source: sportsdataverse-data ``espn_cfb_player_box`` release. Attribute
cfbfastR / sportsdataverse.
"""

from __future__ import annotations

import logging

import polars as pl

from sleeper_ffm.config import CACHE_DIR
from sleeper_ffm.names import normalize_name

log = logging.getLogger(__name__)

_URL = (
    "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
    "espn_cfb_player_box/player_box_{season}.parquet"
)

# In-process cache of loaded season frames (keyed by season year).
_SEASON_FRAMES: dict[int, pl.DataFrame | None] = {}


def _load_season(season: int) -> pl.DataFrame | None:
    """Return the ESPN player-box frame for a season, cached on disk + in memory."""
    if season in _SEASON_FRAMES:
        return _SEASON_FRAMES[season]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"cfb_box_{season}.parquet"
    df: pl.DataFrame | None = None
    if path.exists():
        try:
            df = pl.read_parquet(path)
        except Exception as exc:
            log.warning("cfb_box: cache read failed for %s: %s", season, exc)
            df = None
    if df is None:
        try:
            df = pl.read_parquet(_URL.format(season=season))
            df.write_parquet(path)
        except Exception as exc:
            log.warning("cfb_box: fetch failed for season=%s: %s", season, exc)
            df = None

    _SEASON_FRAMES[season] = df
    return df


def _sum_int(frame: pl.DataFrame, col: str) -> int:
    if col not in frame.columns:
        return 0
    total = frame[col].cast(pl.Float64, strict=False).sum()
    return int(total) if total is not None else 0


def _parse_comp_att(frame: pl.DataFrame) -> tuple[int, int]:
    """Sum ``completions/passingAttempts`` strings like ``"22/31"`` across games."""
    col = "completions/passingAttempts"
    if col not in frame.columns:
        return 0, 0
    comp = att = 0
    for raw in frame[col].to_list():
        if not raw or "/" not in str(raw):
            continue
        left, _, right = str(raw).partition("/")
        try:
            comp += int(left)
            att += int(right)
        except ValueError:
            continue
    return comp, att


def _season_row(sub: pl.DataFrame, season: int) -> dict | None:
    """Aggregate one player's games in one season into receiving/rushing/passing."""
    row: dict = {"season": season}

    rec = sub.filter(pl.col("category") == "receiving")
    catches = _sum_int(rec, "receptions") if rec.height else 0
    if catches:
        yards = _sum_int(rec, "receivingYards")
        row["receiving"] = {
            "games": rec.height,
            "receptions": catches,
            "yards": yards,
            "touchdowns": _sum_int(rec, "receivingTouchdowns"),
            "ypr": round(yards / catches, 1) if catches else 0.0,
        }

    rush = sub.filter(pl.col("category") == "rushing")
    carries = _sum_int(rush, "rushingAttempts") if rush.height else 0
    if carries:
        yards = _sum_int(rush, "rushingYards")
        row["rushing"] = {
            "games": rush.height,
            "carries": carries,
            "yards": yards,
            "touchdowns": _sum_int(rush, "rushingTouchdowns"),
            "ypc": round(yards / carries, 1) if carries else 0.0,
        }

    passing = sub.filter(pl.col("category") == "passing")
    if passing.height:
        comp, att = _parse_comp_att(passing)
        yards = _sum_int(passing, "passingYards")
        if att:
            row["passing"] = {
                "games": passing.height,
                "completions": comp,
                "attempts": att,
                "comp_pct": round(comp / att * 100, 1) if att else 0.0,
                "yards": yards,
                "touchdowns": _sum_int(passing, "passingTouchdowns"),
                "interceptions": _sum_int(passing, "interceptions"),
                "ypa": round(yards / att, 1) if att else 0.0,
            }

    return row if len(row) > 1 else None


def college_history(name: str, draft_year: int, lookback: int = 3) -> list[dict]:
    """Return per-season college production for a player, newest season last.

    Pulls the ``lookback`` college seasons preceding the draft year (a draft
    prospect's final seasons), aggregates each, and keeps only seasons with
    real production. Returns an empty list if no keyless data is available.
    """
    norm = normalize_name(name)
    history: list[dict] = []
    for season in range(draft_year - lookback, draft_year):
        frame = _load_season(season)
        if frame is None or "athlete_name" not in frame.columns:
            continue
        # Normalize both sides identically -- comparing a fully-normalized query name
        # against a merely lowercased/stripped column would silently miss any player
        # whose name has a suffix, punctuation, or an accented character.
        sub = frame.filter(
            pl.col("athlete_name")
            .cast(pl.Utf8)
            .map_elements(normalize_name, return_dtype=pl.Utf8)
            .eq(norm)
        )
        if not sub.height:
            continue
        agg = _season_row(sub, season)
        if agg:
            history.append(agg)
    return history
