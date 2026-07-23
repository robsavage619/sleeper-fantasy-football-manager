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

import json
import logging
from numbers import Real
from typing import TYPE_CHECKING

import polars as pl

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.config import DATA_DIR, DEFAULT_VALUE_SEASON
from sleeper_ffm.market.blend import FC_TO_FPAR_SCALE
from sleeper_ffm.model.dynasty import PlayerAsset
from sleeper_ffm.names import normalize_name
from sleeper_ffm.nflverse.loader import load_id_map, load_pbp, load_weekly
from sleeper_ffm.scoring.engine import load_scoring, score, stats_from_nflverse

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


# Fallback replacement ranks (used if league_settings.json is missing or malformed).
_REPLACEMENT_RANK_FALLBACK: dict[str, int] = {
    "QB": 12,
    "RB": 36,
    "WR": 42,
    "TE": 12,
}

# FLEX allocation fractions — how to split FLEX slots among positions.
_FLEX_ALLOC: dict[str, float] = {"WR": 0.55, "RB": 0.40, "TE": 0.05}


def _derive_replacement_ranks() -> dict[str, int]:
    """Derive replacement ranks from data/league_settings.json.

    Computes (base_slots + flex_alloc) x num_teams for each skill position.
    Falls back to hardcoded dict if the settings file is absent or unparseable.
    """
    settings_path = DATA_DIR / "league_settings.json"
    if not settings_path.exists():
        log.warning("league_settings.json not found; using hardcoded replacement ranks")
        return dict(_REPLACEMENT_RANK_FALLBACK)
    try:
        with settings_path.open() as f:
            settings = json.load(f)
    except Exception as exc:
        log.warning("could not parse league_settings.json (%s); using hardcoded ranks", exc)
        return dict(_REPLACEMENT_RANK_FALLBACK)

    roster_positions: list[str] = settings.get("roster_positions", [])
    num_teams: int = int(settings.get("total_rosters", 10))
    flex_count: int = roster_positions.count("FLEX")

    ranks: dict[str, int] = {}
    for pos in ("QB", "RB", "WR", "TE"):
        base = roster_positions.count(pos)
        flex = flex_count * _FLEX_ALLOC.get(pos, 0.0)
        ranks[pos] = max(1, round((base + flex) * num_teams))

    log.debug("derived replacement ranks from league settings: %s", ranks)
    return ranks


_REPLACEMENT_RANK: dict[str, int] = _derive_replacement_ranks()

SKILL_POSITIONS: frozenset[str] = frozenset({"QB", "RB", "WR", "TE"})


_MIN_GAMES_FOR_PER_GAME_NORM: int = 6  # below this, keep raw season_fp to avoid sample noise
_FULL_SEASON_GAMES: int = 17  # normalize to this game count


def score_weekly(
    seasons: list[int] | None = None,
    scoring: dict[str, float] | None = None,
) -> pl.DataFrame:
    """Score each regular-season game-week; return df with ``fp_sffm`` column.

    Args:
        seasons: Seasons to score (default: latest completed NFL season).
        scoring: Override scoring settings (defaults to league settings).

    Returns:
        Weekly df (REG only) augmented with a ``fp_sffm`` column.
    """
    seasons = seasons or [DEFAULT_VALUE_SEASON]
    scoring = scoring or load_scoring()

    weekly = load_weekly(seasons=seasons)
    if weekly.is_empty() or "season_type" not in weekly.columns:
        return _empty_scored_weekly()
    reg = weekly.filter(pl.col("season_type") == "REG")
    if reg.is_empty():
        return _empty_scored_weekly()

    reg = _attach_long_td_bonuses(reg, seasons)

    fps = [score(stats_from_nflverse(row), scoring) for row in reg.iter_rows(named=True)]
    return reg.with_columns(pl.Series("fp_sffm", fps, dtype=pl.Float64))


# Length threshold for the long-touchdown bonuses. A box score records that a
# touchdown happened, not how far it travelled, so these can only come from
# play-by-play — without them the *_td_40p bonuses silently score as zero.
_TD40_YARDS = 40

# Earliest season with play-by-play coverage. Older seasons score without long-TD
# bonuses, which understates them; the gap is logged rather than hidden.
_PBP_FIRST_SEASON = 2016


@ttl_cache(key=lambda seasons: tuple(sorted(seasons)))
def long_td_counts(seasons: list[int]) -> pl.DataFrame:
    """Count each player's 40+ yard touchdowns per week, split by scoring type.

    Args:
        seasons: Seasons to scan. Seasons without play-by-play coverage are skipped.

    Returns:
        ``player_id`` / ``season`` / ``week`` rows carrying ``rec_td_40p``,
        ``rush_td_40p`` and ``pass_td_40p`` counts. Empty when no pbp is cached.
    """
    covered = [s for s in seasons if s >= _PBP_FIRST_SEASON]
    if not covered:
        return _empty_long_td_frame()

    try:
        pbp = load_pbp(seasons=covered)
    except (FileNotFoundError, OSError) as exc:
        log.warning("long_td_counts: play-by-play unavailable (%s); long-TD bonuses omitted", exc)
        return _empty_long_td_frame()
    if pbp.is_empty():
        return _empty_long_td_frame()

    big = pbp.filter(
        pl.col("season_type").eq("REG")
        & pl.col("touchdown").eq(1)
        & pl.col("yards_gained").ge(_TD40_YARDS)
    )
    if big.is_empty():
        return _empty_long_td_frame()

    def _side(mask: pl.Expr, id_col: str, alias: str) -> pl.DataFrame:
        return (
            big.filter(mask & pl.col(id_col).is_not_null())
            .group_by(["season", "week", id_col])
            .len(alias)
            .rename({id_col: "player_id"})
        )

    rec = _side(pl.col("pass_touchdown").eq(1), "receiver_player_id", "rec_td_40p")
    rush = _side(pl.col("rush_touchdown").eq(1), "rusher_player_id", "rush_td_40p")
    passing = _side(pl.col("pass_touchdown").eq(1), "passer_player_id", "pass_td_40p")

    merged = rec.join(rush, on=["season", "week", "player_id"], how="full", coalesce=True).join(
        passing, on=["season", "week", "player_id"], how="full", coalesce=True
    )
    return merged.with_columns(
        pl.col(["rec_td_40p", "rush_td_40p", "pass_td_40p"]).fill_null(0).cast(pl.Int64)
    )


def _empty_long_td_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "season": pl.Int64,
            "week": pl.Int64,
            "player_id": pl.Utf8,
            "rec_td_40p": pl.Int64,
            "rush_td_40p": pl.Int64,
            "pass_td_40p": pl.Int64,
        }
    )


def _attach_long_td_bonuses(reg: pl.DataFrame, seasons: list[int]) -> pl.DataFrame:
    """Join per-week long-touchdown counts onto weekly rows so ``score`` can pay them."""
    counts = long_td_counts(seasons)
    bonus_cols = ["rec_td_40p", "rush_td_40p", "pass_td_40p"]

    if counts.is_empty():
        return reg.with_columns([pl.lit(0, dtype=pl.Int64).alias(c) for c in bonus_cols])

    uncovered = sorted(s for s in seasons if s < _PBP_FIRST_SEASON)
    if uncovered:
        log.info(
            "long-TD bonuses unavailable for seasons %s (pbp starts %d); those seasons "
            "score without them",
            uncovered,
            _PBP_FIRST_SEASON,
        )

    joined = reg.join(
        counts.cast({"season": reg.schema["season"], "week": reg.schema["week"]}),
        on=["player_id", "season", "week"],
        how="left",
    )
    return joined.with_columns([pl.col(c).fill_null(0) for c in bonus_cols])


def compute_season_totals(
    seasons: list[int] | None = None,
    scoring: dict[str, float] | None = None,
) -> pl.DataFrame:
    """Score weekly data and aggregate to player-season totals.

    Returns a DataFrame with columns:
        ``gsis_id``, ``season``, ``position``, ``name``, ``team``,
        ``season_fp``, ``games_played``, ``sleeper_id_str``

    Args:
        seasons: Seasons to process (default: latest completed NFL season).
        scoring: Override scoring settings.
    """
    seasons = seasons or [DEFAULT_VALUE_SEASON]
    scored = score_weekly(seasons=seasons, scoring=scoring)
    if scored.is_empty():
        return _empty_season_totals()

    season_totals = (
        scored.filter(pl.col("position").is_in(list(SKILL_POSITIONS)))
        .group_by(["player_id", "season", "position"])
        .agg(
            [
                pl.col("fp_sffm").sum().alias("season_fp"),
                pl.col("fp_sffm").len().alias("games_played"),
                pl.col("player_display_name").first().alias("name"),
                pl.col("recent_team").last().alias("team"),
            ]
        )
        .filter(pl.col("season_fp") > 0)
        # Normalize to 17-game equivalent; small-sample players kept raw to avoid inflation.
        .with_columns(
            pl.when(pl.col("games_played") >= _MIN_GAMES_FOR_PER_GAME_NORM)
            .then(pl.col("season_fp") / pl.col("games_played") * _FULL_SEASON_GAMES)
            .otherwise(pl.col("season_fp"))
            .alias("season_fp")
        )
        .rename({"player_id": "gsis_id"})
    )

    # Join Sleeper IDs from the crosswalk
    id_map = load_id_map()
    id_slim = (
        id_map.select(["gsis_id", "sleeper_id"])
        .filter(pl.col("gsis_id").is_not_null() & pl.col("sleeper_id").is_not_null())
        .with_columns(
            pl.col("sleeper_id").cast(pl.Int64, strict=False).cast(pl.Utf8).alias("sleeper_id_str")
        )
        .filter(pl.col("sleeper_id_str").is_not_null())
        .select(["gsis_id", "sleeper_id_str"])
    )

    return season_totals.join(id_slim, on="gsis_id", how="left")


def _empty_scored_weekly() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "season": pl.Int64,
            "week": pl.Int64,
            "season_type": pl.Utf8,
            "player_id": pl.Utf8,
            "position": pl.Utf8,
            "player_display_name": pl.Utf8,
            "recent_team": pl.Utf8,
            "fp_sffm": pl.Float64,
        }
    )


def _empty_season_totals() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "gsis_id": pl.Utf8,
            "season": pl.Int64,
            "position": pl.Utf8,
            "season_fp": pl.Float64,
            "games_played": pl.Float64,
            "name": pl.Utf8,
            "team": pl.Utf8,
            "sleeper_id_str": pl.Utf8,
        }
    )


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
        pos_df = totals.filter(pl.col("position") == pos).sort("season_fp", descending=True)
        if len(pos_df) >= rank:
            thresholds[pos] = float(pos_df["season_fp"][rank - 1])
        else:
            # Shallow position or limited data: use minimum.
            thresholds[pos] = _float_or_zero(pos_df["season_fp"].min())
        log.debug("replacement[%s] = %.1f", pos, thresholds[pos])
    return thresholds


def _float_or_zero(value: object) -> float:
    if isinstance(value, Real):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _rookie_fpar(search_rank: int) -> float:
    """Map Sleeper dynasty search_rank to an estimated FPAR for unproven players.

    Fallback when FantasyCalc has no value for the player.
    A convex decay: rank 1 ≈ 95 FPAR, rank 20 ≈ 50, rank 50 ≈ 29, rank 100 ≈ 17.
    """
    return round(100.0 / (1.0 + search_rank / 20.0), 2)


def build_rookie_assets(
    sleeper_players: dict[str, dict],
    rostered_ids: set[str],
    max_rank: int = 300,
    market_values: dict[str, float] | None = None,
) -> list[PlayerAsset]:
    """Build PlayerAsset objects for rookies / year-1 players not yet rostered.

    Uses FantasyCalc dynasty value (if available via ``market_values``) to
    estimate FPAR, falling back to Sleeper's ``search_rank`` heuristic when
    no market price is available for the player.

    Args:
        sleeper_players: Sleeper player dump from ``SleeperClient.players()``.
        rostered_ids: Player IDs currently on a fantasy roster (excluded).
        max_rank: Ignore players ranked worse than this threshold.
        market_values: {sleeper_id: fc_value} from FantasyCalc (optional).

    Returns:
        List of PlayerAsset sorted by current_fpar descending.
    """
    market_values = market_values or {}
    fc_hits = 0

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

        fc_val = market_values.get(pid)
        if fc_val is not None:
            fpar = round(fc_val / FC_TO_FPAR_SCALE, 2)
            fc_hits += 1
        else:
            fpar = _rookie_fpar(search_rank)

        assets.append(
            PlayerAsset(
                player_id=pid,
                name=p.get("full_name") or f"Player {pid}",
                position=pos,
                age=float(p.get("age") or 22),
                current_fpar=fpar,
                team=p.get("team") or "",
                is_taxi=True,  # rookies default to taxi-squad consideration
            )
        )

    if market_values:
        log.info("build_rookie_assets: %d/%d rookies valued via FC market", fc_hits, len(assets))

    return sorted(assets, key=lambda p: p.current_fpar, reverse=True)


# Recency-weighted blend for the two-season default, derived from the configured
# value season so it rolls over on its own. Hardcoded season keys went stale
# silently: the year after a rollover the newer season would miss the map and
# fall to the 1/n default, weighting the OLDER season more heavily (0.565/0.435).
_PRIOR_SEASON_WEIGHT = 0.35
_LATEST_SEASON_WEIGHT = 0.65
_SEASON_WEIGHTS: dict[int, float] = {
    DEFAULT_VALUE_SEASON - 1: _PRIOR_SEASON_WEIGHT,
    DEFAULT_VALUE_SEASON: _LATEST_SEASON_WEIGHT,
}


def _blend_seasons(totals: pl.DataFrame, seasons: list[int]) -> pl.DataFrame:
    """Recency-weighted blend of per-season (17g-normalized) FPAR.

    Players present in only one season get that season's weight renormalized to 1.
    Players in both seasons get the configured weight split.

    Args:
        totals: Output of compute_season_totals for all requested seasons.
        seasons: Seasons that were requested (used to assign weights).

    Returns:
        Blended DataFrame with one row per (gsis_id, position).
    """
    available = sorted(s for s in seasons if not totals.filter(pl.col("season") == s).is_empty())
    if not available:
        return _empty_season_totals()

    if len(available) == 1:
        return (
            totals.filter(pl.col("season") == available[0])
            .group_by(["gsis_id", "position"])
            .agg(
                [
                    pl.col("season_fp").mean().alias("season_fp"),
                    pl.col("games_played").mean().alias("games_played"),
                    pl.col("name").last().alias("name"),
                    pl.col("team").last().alias("team"),
                    pl.col("sleeper_id_str").last().alias("sleeper_id_str"),
                ]
            )
        )

    raw_weights = {s: _SEASON_WEIGHTS.get(s, 1.0 / len(available)) for s in available}
    total_w = sum(raw_weights.values())
    weights = {s: w / total_w for s, w in raw_weights.items()}
    log.info("season blend weights: %s", {s: round(w, 3) for s, w in weights.items()})

    weighted_frames = []
    for s in available:
        w = weights[s]
        frame = (
            totals.filter(pl.col("season") == s)
            .with_columns((pl.col("season_fp") * w).alias("weighted_fp"))
            .select(
                [
                    "gsis_id",
                    "position",
                    "weighted_fp",
                    "games_played",
                    "name",
                    "team",
                    "sleeper_id_str",
                ]
            )
        )
        weighted_frames.append(frame)

    combined = pl.concat(weighted_frames)
    return combined.group_by(["gsis_id", "position"]).agg(
        [
            pl.col("weighted_fp").sum().alias("season_fp"),
            pl.col("games_played").mean().alias("games_played"),
            pl.col("name").last().alias("name"),
            pl.col("team").last().alias("team"),
            pl.col("sleeper_id_str").last().alias("sleeper_id_str"),
        ]
    )


def build_player_assets(
    seasons: list[int] | None = None,
    scoring: dict[str, float] | None = None,
    sleeper_players: dict[str, dict] | None = None,
) -> list[PlayerAsset]:
    """Build a full ranked list of PlayerAssets from nflverse + Sleeper data.

    Default blend: seasons [2024, 2025] with recency weights 0.35/0.65.
    When 2025 data is unavailable (nflverse 404), falls back to 2024 only
    with a warning — never silently uses stale data as if it were current.

    Args:
        seasons: Seasons to use (default: [2024, PREFERRED_VALUE_SEASON]).
        scoring: Override scoring settings.
        sleeper_players: Pre-fetched Sleeper player dump. Fetched live if None.

    Returns:
        PlayerAsset list sorted by ``current_fpar`` descending.
    """
    from sleeper_ffm.sleeper.client import SleeperClient

    if seasons is None:
        seasons = [DEFAULT_VALUE_SEASON - 1, DEFAULT_VALUE_SEASON]
        seasons = [s for s in seasons if s >= 2014]

    log.info("building player assets from seasons %s", seasons)

    totals = compute_season_totals(seasons=seasons, scoring=scoring)

    available_seasons = sorted(totals["season"].unique().to_list()) if not totals.is_empty() else []
    missing = [s for s in seasons if s not in available_seasons]
    if missing:
        log.warning(
            "seasons %s requested but not available (nflverse data missing); blend uses %s only",
            missing,
            available_seasons,
        )

    avg_totals = _blend_seasons(totals, seasons)

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
            norm = normalize_name(p.get("full_name") or "")
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
                norm = normalize_name(row.get("name") or "")
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


@ttl_cache(key=lambda seasons=None, sleeper_players=None: tuple(seasons) if seasons else "default")
def build_player_assets_cached(
    seasons: list[int] | None = None,
    sleeper_players: dict[str, dict] | None = None,
) -> list[PlayerAsset]:
    """TTL-cached ``build_player_assets`` for default league scoring.

    Keyed on ``seasons`` only (the Sleeper dump is always the live one), so the
    per-partner dossier/roster calls in one request share a single valuation
    instead of re-scoring the weekly data N times.
    """
    return build_player_assets(seasons=seasons, sleeper_players=sleeper_players)


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
        seasons: Seasons for veteran FPAR (default: latest completed NFL season).
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

    # Veterans: use nflverse FPAR, filter to unrostered. Default league scoring
    # shares the TTL-cached valuation — the draft board polls every 15 seconds and
    # re-scoring the weekly data each time is the difference between an instant
    # board and a multi-second one. A scoring override has to be scored fresh,
    # since the cache is keyed on seasons alone.
    vet_assets = (
        build_player_assets_cached(seasons=seasons, sleeper_players=sleeper_players)
        if scoring is None
        else build_player_assets(seasons=seasons, scoring=scoring, sleeper_players=sleeper_players)
    )
    vet_unrostered = [
        asset
        for asset in vet_assets
        if asset.player_id not in rostered_ids and _is_draftable_veteran(asset, sleeper_players)
    ]

    # Fetch FantasyCalc market values once; pass to rookie builder for pricing.
    try:
        from sleeper_ffm.market.fantasycalc import fetch as _fc_fetch

        market_values = _fc_fetch()
    except Exception as exc:
        log.warning("build_draft_pool: FC fetch failed (%s); using search_rank heuristic", exc)
        market_values = {}

    # Rookies / unproven year-1 players
    rookie_assets = build_rookie_assets(
        sleeper_players=sleeper_players,
        rostered_ids=rostered_ids,
        max_rank=rookie_max_rank,
        market_values=market_values,
    )

    # Deduplicate by player_id (veteran list wins if the same player appears in both)
    seen: set[str] = set()
    pool: list[PlayerAsset] = []
    for p in vet_unrostered + rookie_assets:
        if p.player_id not in seen:
            seen.add(p.player_id)
            pool.append(p)

    return sorted(pool, key=lambda p: p.current_fpar, reverse=True)


def _is_draftable_veteran(asset: PlayerAsset, sleeper_players: dict[str, dict]) -> bool:
    player = sleeper_players.get(asset.player_id, {})
    years_exp = player.get("years_exp")
    search_rank = int(player.get("search_rank") or 9999)
    has_team = bool(player.get("team") or asset.team)
    if not has_team:
        return False
    if asset.age > 25.5:
        return False
    if years_exp is not None and years_exp > 2:
        return False
    return search_rank <= 450
