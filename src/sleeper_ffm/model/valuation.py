"""Player valuation: nflverse weekly data → scored season FPAR → PlayerAsset objects.

Pipeline:
    1. Load nflverse weekly parquet for the requested season(s)
    2. Score each regular-season game-week via ``scoring.engine.score()``
    3. Aggregate to season totals per player-season
    4. Compute FPAR = season_fp - position replacement threshold
    5. Join with Sleeper player dump for age, name, team
    6. Return ``PlayerAsset`` objects ready for ``model.dynasty.value_player()``

Replacement thresholds are computed empirically from the data: the total
fantasy points of the Nth-ranked player at each position, where N reflects
the starter slots in a 10-team 1QB dynasty (QB12, RB36, WR42, TE12).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import polars as pl

from sleeper_ffm.model.dynasty import PlayerAsset
from sleeper_ffm.nflverse.loader import load_id_map, load_weekly
from sleeper_ffm.scoring.engine import load_scoring, score, stats_from_nflverse

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

_SUFFIX_RE = re.compile(r"\s+(jr\.?|sr\.?|ii|iii|iv|v)$", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^a-z\s]")


def _normalize_name(name: str) -> str:
    """Lowercase, strip name suffixes (Jr./Sr./II/III/IV) and punctuation, collapse whitespace."""
    name = name.lower().strip()
    name = _SUFFIX_RE.sub("", name)
    name = _PUNCT_RE.sub("", name)
    return " ".join(name.split())


# Replacement rank per position for a 10-team 1QB dynasty.
# Player at this rank is the baseline "available on waivers" level.
_REPLACEMENT_RANK: dict[str, int] = {
    "QB": 12,   # 1 QB x 10 + 2 cushion
    "RB": 36,   # 3 RB x 10 + 6 FLEX slots
    "WR": 42,   # 3 WR x 10 + 12 FLEX slots
    "TE": 12,   # 1 TE x 10 + 2 cushion
}

SKILL_POSITIONS: frozenset[str] = frozenset({"QB", "RB", "WR", "TE"})


def score_weekly(
    seasons: list[int] | None = None,
    scoring: dict[str, float] | None = None,
) -> pl.DataFrame:
    """Score each regular-season game-week; return df with ``fp_sffm`` column.

    Args:
        seasons: Seasons to score (default: [2024]).
        scoring: Override scoring settings (defaults to league settings).

    Returns:
        Weekly df (REG only) augmented with a ``fp_sffm`` column.
    """
    seasons = seasons or [2024]
    scoring = scoring or load_scoring()

    weekly = load_weekly(seasons=seasons)
    reg = weekly.filter(pl.col("season_type") == "REG")

    fps = [
        score(stats_from_nflverse(row), scoring)
        for row in reg.iter_rows(named=True)
    ]
    return reg.with_columns(pl.Series("fp_sffm", fps, dtype=pl.Float64))


def compute_season_totals(
    seasons: list[int] | None = None,
    scoring: dict[str, float] | None = None,
) -> pl.DataFrame:
    """Score weekly data and aggregate to player-season totals.

    Returns a DataFrame with columns:
        ``gsis_id``, ``season``, ``position``, ``name``, ``team``,
        ``season_fp``, ``games_played``, ``sleeper_id_str``

    Args:
        seasons: Seasons to process (default: [2024]).
        scoring: Override scoring settings.
    """
    seasons = seasons or [2024]
    scored = score_weekly(seasons=seasons, scoring=scoring)

    season_totals = (
        scored
        .filter(pl.col("position").is_in(list(SKILL_POSITIONS)))
        .group_by(["player_id", "season", "position"])
        .agg([
            pl.col("fp_sffm").sum().alias("season_fp"),
            pl.col("fp_sffm").len().alias("games_played"),
            pl.col("player_display_name").first().alias("name"),
            pl.col("recent_team").last().alias("team"),
        ])
        .filter(pl.col("season_fp") > 0)
        .rename({"player_id": "gsis_id"})
    )

    # Join Sleeper IDs from the crosswalk
    id_map = load_id_map()
    id_slim = (
        id_map
        .select(["gsis_id", "sleeper_id"])
        .filter(
            pl.col("gsis_id").is_not_null()
            & pl.col("sleeper_id").is_not_null()
        )
        .with_columns(
            pl.col("sleeper_id")
            .cast(pl.Int64, strict=False)
            .cast(pl.Utf8)
            .alias("sleeper_id_str")
        )
        .filter(pl.col("sleeper_id_str").is_not_null())
        .select(["gsis_id", "sleeper_id_str"])
    )

    return season_totals.join(id_slim, on="gsis_id", how="left")


def replacement_thresholds(totals: pl.DataFrame) -> dict[str, float]:
    """Derive position replacement FP thresholds from actual data.

    For each position, the replacement level is the season_fp of the player
    ranked at ``_REPLACEMENT_RANK[pos]``. Players below this line are
    replacement-level and have zero dynasty value.

    Args:
        totals: Output of :func:`compute_season_totals` (or an aggregate of
            the same shape). Must have ``position`` and ``season_fp`` columns.

    Returns:
        Dict mapping position string to replacement-level season FP.
    """
    thresholds: dict[str, float] = {}
    for pos, rank in _REPLACEMENT_RANK.items():
        pos_df = totals.filter(pl.col("position") == pos).sort(
            "season_fp", descending=True
        )
        if len(pos_df) >= rank:
            thresholds[pos] = float(pos_df["season_fp"][rank - 1])
        else:
            # Shallow position (off-season / limited data) — use minimum
            thresholds[pos] = float(pos_df["season_fp"].min() or 0.0)
        log.debug("replacement[%s] = %.1f", pos, thresholds[pos])
    return thresholds


def _rookie_fpar(search_rank: int) -> float:
    """Map Sleeper dynasty search_rank to an estimated FPAR for unproven players.

    A convex decay: rank 1 ≈ 95 FPAR, rank 20 ≈ 50, rank 50 ≈ 29, rank 100 ≈ 17.
    Calibrated so that top rookies are valued roughly as WR3/RB3 veterans
    (significant upside; not yet proven NFL producers).
    """
    return round(100.0 / (1.0 + search_rank / 20.0), 2)


def build_rookie_assets(
    sleeper_players: dict[str, dict],
    rostered_ids: set[str],
    max_rank: int = 300,
) -> list[PlayerAsset]:
    """Build PlayerAsset objects for rookies / year-1 players not yet rostered.

    Uses Sleeper's ``search_rank`` (dynasty ranking) as a proxy for FPAR since
    these players have no nflverse history. Only players with NFL teams are
    included (cuts undrafted practice-squad players without clear value).

    Args:
        sleeper_players: Sleeper player dump from ``SleeperClient.players()``.
        rostered_ids: Player IDs currently on a fantasy roster (excluded).
        max_rank: Ignore players ranked worse than this threshold.

    Returns:
        List of PlayerAsset sorted by current_fpar descending.
    """
    assets: list[PlayerAsset] = []
    for pid, p in sleeper_players.items():
        years_exp = p.get("years_exp")
        if years_exp is None or years_exp > 1:
            continue
        pos = p.get("position", "")
        if pos not in SKILL_POSITIONS:
            continue
        if not p.get("team"):  # no NFL team = not relevant for dynasty rookie draft
            continue
        if pid in rostered_ids:
            continue
        search_rank: int | None = p.get("search_rank")
        if search_rank is None or search_rank >= max_rank:
            continue
        assets.append(
            PlayerAsset(
                player_id=pid,
                name=p.get("full_name") or f"Player {pid}",
                position=pos,
                age=float(p.get("age") or 22),
                current_fpar=_rookie_fpar(search_rank),
                team=p.get("team") or "",
                is_taxi=True,  # rookies default to taxi-squad consideration
            )
        )
    return sorted(assets, key=lambda p: p.current_fpar, reverse=True)


def build_player_assets(
    seasons: list[int] | None = None,
    scoring: dict[str, float] | None = None,
    sleeper_players: dict[str, dict] | None = None,
) -> list[PlayerAsset]:
    """Build a full ranked list of PlayerAssets from nflverse + Sleeper data.

    Uses the most recent season in ``seasons`` as the current FPAR estimate.
    Multiple seasons are averaged for a more stable estimate (recent-weighted
    when ordered — caller should pass most recent last to get correct average).

    Args:
        seasons: Seasons to use (default [2024]). More seasons = smoother FPAR.
        scoring: Override scoring settings.
        sleeper_players: Pre-fetched Sleeper player dump. Fetched live if None.

    Returns:
        PlayerAsset list sorted by ``current_fpar`` descending.
    """
    from sleeper_ffm.sleeper.client import SleeperClient

    seasons = seasons or [2024]
    log.info("building player assets from seasons %s", seasons)

    totals = compute_season_totals(seasons=seasons, scoring=scoring)

    # For multi-season: average season_fp across seasons per player.
    if len(seasons) > 1:
        avg_totals = (
            totals
            .group_by(["gsis_id", "position"])
            .agg([
                pl.col("season_fp").mean().alias("season_fp"),
                pl.col("games_played").mean().alias("games_played"),
                pl.col("name").last().alias("name"),
                pl.col("team").last().alias("team"),
                pl.col("sleeper_id_str").last().alias("sleeper_id_str"),
            ])
        )
    else:
        avg_totals = totals

    thresholds = replacement_thresholds(avg_totals)

    if sleeper_players is None:
        with SleeperClient() as c:
            sleeper_players = c.players()

    # Build supplementary ID indexes to cover gaps in the nflverse crosswalk.
    # Primary resolution (crosswalk gsis_id → sleeper_id) is already in avg_totals.sleeper_id_str.
    # Fallback 1: Sleeper's own gsis_id field (often populated where the crosswalk is missing).
    # Fallback 2: normalized full_name + position (unique match only; ambiguous = skip).
    sleeper_by_gsis: dict[str, str] = {}
    sleeper_by_name_pos: dict[tuple[str, str], str] = {}  # "" means ambiguous duplicate

    for pid, p in sleeper_players.items():
        gsis = p.get("gsis_id") or ""
        if gsis:
            sleeper_by_gsis[gsis] = pid

        pos = p.get("position", "")
        if pos in SKILL_POSITIONS:
            norm = _normalize_name(p.get("full_name") or "")
            if norm:
                key = (norm, pos)
                if key in sleeper_by_name_pos:
                    sleeper_by_name_pos[key] = ""  # mark ambiguous
                else:
                    sleeper_by_name_pos[key] = pid

    xwalk_hits = 0
    sgsis_hits = 0
    name_hits = 0

    assets: list[PlayerAsset] = []
    for row in avg_totals.iter_rows(named=True):
        pos = row["position"]
        if pos not in SKILL_POSITIONS:
            continue

        sid: str | None = row.get("sleeper_id_str")

        if sid:
            xwalk_hits += 1
        else:
            # Fallback 1: Sleeper's own gsis_id field
            sid = sleeper_by_gsis.get(row["gsis_id"])
            if sid:
                sgsis_hits += 1
            else:
                # Fallback 2: name + position (skip if ambiguous)
                norm = _normalize_name(row.get("name") or "")
                candidate = sleeper_by_name_pos.get((norm, pos), "")
                if candidate:
                    sid = candidate
                    name_hits += 1

        sp = sleeper_players.get(sid or "", {})

        # Prefer Sleeper player dump for metadata (more current than nflverse)
        age = float(sp.get("age") or 26)
        name: str = sp.get("full_name") or row.get("name") or "Unknown"
        # Use Sleeper team if present; empty string means FA (more current than nflverse)
        team: str = sp.get("team") or ("FA" if sp else (row.get("team") or ""))

        repl = thresholds.get(pos, 0.0)
        fpar = max(0.0, float(row["season_fp"]) - repl)

        assets.append(
            PlayerAsset(
                player_id=sid or row["gsis_id"],
                name=name,
                position=pos,
                age=age,
                current_fpar=round(fpar, 2),
                team=team,
            )
        )

    gsis_total = xwalk_hits + sgsis_hits
    log.info(
        "ID map: %d players resolved (%d gsis + %d name fallback)",
        gsis_total + name_hits,
        gsis_total,
        name_hits,
    )

    return sorted(assets, key=lambda p: p.current_fpar, reverse=True)


def build_draft_pool(
    rostered_ids: set[str],
    seasons: list[int] | None = None,
    scoring: dict[str, float] | None = None,
    sleeper_players: dict[str, dict] | None = None,
    rookie_max_rank: int = 300,
) -> list[PlayerAsset]:
    """Build the full available pool for a dynasty rookie/offseason draft.

    Merges:
      - Veterans with nflverse FPAR (unrostered only)
      - Rookies / year-1 players ranked by Sleeper dynasty ``search_rank``

    Veterans dominate in FPAR only if they had elite production above replacement.
    Most roster-worthy players in this pool are incoming rookies.

    Args:
        rostered_ids: Set of Sleeper player IDs already on a fantasy roster.
        seasons: Seasons for veteran FPAR (default [2024]).
        scoring: Override scoring settings.
        sleeper_players: Pre-fetched player dump (fetched live if None).
        rookie_max_rank: Discard rookies ranked worse than this.

    Returns:
        Merged list sorted by ``current_fpar`` descending.
    """
    from sleeper_ffm.sleeper.client import SleeperClient

    if sleeper_players is None:
        with SleeperClient() as c:
            sleeper_players = c.players()

    # Veterans: use nflverse FPAR, filter to unrostered
    vet_assets = build_player_assets(
        seasons=seasons, scoring=scoring, sleeper_players=sleeper_players
    )
    vet_unrostered = [a for a in vet_assets if a.player_id not in rostered_ids]

    # Rookies / unproven year-1 players
    rookie_assets = build_rookie_assets(
        sleeper_players=sleeper_players,
        rostered_ids=rostered_ids,
        max_rank=rookie_max_rank,
    )

    # Deduplicate by player_id (veteran list wins if the same player appears in both)
    seen: set[str] = set()
    pool: list[PlayerAsset] = []
    for p in vet_unrostered + rookie_assets:
        if p.player_id not in seen:
            seen.add(p.player_id)
            pool.append(p)

    return sorted(pool, key=lambda p: p.current_fpar, reverse=True)
