"""In-house player sabermetrics computed under THIS league's exact scoring.

Every fantasy-point figure flows from ``scoring.engine`` via ``valuation.score_weekly``, so
metrics reflect the commissioner's settings, not generic PPR. The module is split into pure,
hand-verifiable helper functions (unit-tested against a frozen fixture) and a thin orchestrator
``build_player_sabermetrics`` that pulls live nflverse data and assembles the suite.

Slice A (production-grade, direct from parquet):
    - consistency profile (floor/median/ceiling, volatility, boom%/bust%)
    - TD dependence vs positional median
    - opportunity trend (snap / target / carry, last-4 vs prior)
    - age-curve residual (actual FPAR vs age-arc projection off the prior season)
    - market momentum (FantasyCalc trend30Day)
    - usage-quality panel (wopr, target/air-yards share, racr, EPA, CPOE, explosive rate, snaps)

Slice B (labelled UNCALIBRATED, carries evidence_count):
    - xFP + efficiency residual (usage-expected FP vs actual)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import polars as pl

from sleeper_ffm.config import CURRENT_LEAGUE_YEAR, DEFAULT_VALUE_SEASON, cached_weekly_seasons
from sleeper_ffm.model.dynasty import _ASCENT_RATE, _DECAY_RATE, _PEAK_AGE
from sleeper_ffm.model.valuation import _normalize_name, score_weekly
from sleeper_ffm.nflverse.loader import load_id_map, load_snaps
from sleeper_ffm.scoring.engine import load_scoring
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

SKILL_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")

# Weekly rank a fantasy starter must clear to count as "startable" (10-team, 1QB, full PPR).
_STARTER_WEEKLY_RANK: dict[str, int] = {"QB": 10, "RB": 24, "WR": 30, "TE": 10}
# Weekly rank below which a week is replacement-level ("bust"): starters + one bench round.
_REPLACEMENT_WEEKLY_RANK: dict[str, int] = {"QB": 14, "RB": 36, "WR": 44, "TE": 14}

# Fallback absolute FP thresholds when the weekly distribution is too thin to derive them.
_FALLBACK_STARTABLE: dict[str, float] = {"QB": 18.0, "RB": 12.0, "WR": 12.0, "TE": 9.0}
_FALLBACK_REPLACEMENT: dict[str, float] = {"QB": 12.0, "RB": 7.0, "WR": 7.0, "TE": 5.0}


# ---------------------------------------------------------------------------
# Pure statistical helpers (unit-tested directly)
# ---------------------------------------------------------------------------


def _percentile(values: list[float], q: float) -> float:
    """Return the ``q``-th percentile (0-100) via linear interpolation (numpy 'linear')."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (q / 100.0) * (len(ordered) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (rank - lo) * (ordered[hi] - ordered[lo])


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pstdev(values: list[float]) -> float:
    """Population standard deviation (deterministic; used for coefficient of variation)."""
    if len(values) < 2:
        return 0.0
    mu = _mean(values)
    return math.sqrt(sum((v - mu) ** 2 for v in values) / len(values))


def rank_threshold(week_scores: list[float], rank: int) -> float:
    """Return the fantasy score of the ``rank``-th best player in one week (1-indexed).

    If fewer than ``rank`` players scored, returns the lowest score present.
    """
    if not week_scores:
        return 0.0
    ordered = sorted(week_scores, reverse=True)
    idx = min(rank, len(ordered)) - 1
    return ordered[idx]


def consistency_profile(
    weekly_fp: list[float], startable: float, replacement: float
) -> dict[str, float | int | None]:
    """Compute floor/median/ceiling, volatility, and boom%/bust% for one player-season.

    Args:
        weekly_fp: Weekly fantasy points (this league's scoring).
        startable: FP a week must reach to count as a boom (positional starter line).
        replacement: FP below which a week counts as a bust (positional replacement line).

    Returns:
        Dict with floor (p20), median, ceiling (p90), volatility (CV), boom_pct, bust_pct, games.
    """
    n = len(weekly_fp)
    if n == 0:
        return {
            "games": 0,
            "floor": None,
            "median": None,
            "ceiling": None,
            "volatility": None,
            "boom_pct": None,
            "bust_pct": None,
        }
    mu = _mean(weekly_fp)
    volatility = round(_pstdev(weekly_fp) / mu, 3) if mu > 0 else None
    return {
        "games": n,
        "floor": round(_percentile(weekly_fp, 20), 2),
        "median": round(_percentile(weekly_fp, 50), 2),
        "ceiling": round(_percentile(weekly_fp, 90), 2),
        "volatility": volatility,
        "boom_pct": round(sum(1 for v in weekly_fp if v >= startable) / n, 3),
        "bust_pct": round(sum(1 for v in weekly_fp if v < replacement) / n, 3),
    }


def td_dependence(td_points: float, total_fp: float) -> float | None:
    """Return share of fantasy points derived from touchdowns (None if no production)."""
    if total_fp <= 0:
        return None
    return round(td_points / total_fp, 3)


def opportunity_trend(series: list[float], window: int = 4) -> float | None:
    """Return mean(last ``window``) minus mean(prior weeks); None if either side is empty."""
    if len(series) <= window:
        return None
    recent = series[-window:]
    prior = series[:-window]
    if not prior:
        return None
    return round(_mean(recent) - _mean(prior), 3)


def age_curve_expected(prior_fpar: float, prior_age: float, position: str) -> float:
    """Project a player's FPAR one season forward along the position age arc.

    Pre-peak seasons grow by the position ascent rate; peak-or-later seasons decay. This mirrors
    the factors ``dynasty.value_player`` applies year over year (imported, never mutated).
    """
    peak = _PEAK_AGE.get(position, 26)
    ascent = _ASCENT_RATE.get(position, 1.05)
    decay = _DECAY_RATE.get(position, 0.88)
    factor = ascent if prior_age + 1 <= peak else decay
    return round(prior_fpar * factor, 3)


def age_curve_residual(actual_fpar: float, expected_fpar: float) -> float:
    """Actual FPAR minus age-arc expectation; positive = outperforming the age curve."""
    return round(actual_fpar - expected_fpar, 3)


def expected_fp(opportunities: dict[str, float], coeffs: dict[str, float]) -> float:
    """Usage-based expected fantasy points: sum(opportunity[k] * coeff[k]) over shared keys."""
    return round(sum(opportunities.get(k, 0.0) * c for k, c in coeffs.items()), 3)


# ---------------------------------------------------------------------------
# Threshold derivation from the full weekly distribution
# ---------------------------------------------------------------------------


def weekly_positional_thresholds(weekly: pl.DataFrame) -> dict[str, dict[str, float]]:
    """Derive per-position startable / replacement weekly FP lines from the league distribution.

    For each position and each (season, week), the startable line is the FP of the player ranked
    at the positional starter rank, and the replacement line is the FP at the deeper replacement
    rank. Both are averaged across weeks. Falls back to fixed absolute lines for thin positions.

    Args:
        weekly: Scored weekly frame with ``position``, ``season``, ``week``, ``fp_sffm`` columns.

    Returns:
        ``{pos: {"startable": x, "replacement": y}}`` for each skill position.
    """
    thresholds: dict[str, dict[str, float]] = {}
    for pos in SKILL_POSITIONS:
        start_rank = _STARTER_WEEKLY_RANK[pos]
        repl_rank = _REPLACEMENT_WEEKLY_RANK[pos]
        pos_df = weekly.filter(pl.col("position") == pos)
        if pos_df.is_empty():
            thresholds[pos] = {
                "startable": _FALLBACK_STARTABLE[pos],
                "replacement": _FALLBACK_REPLACEMENT[pos],
            }
            continue
        start_lines: list[float] = []
        repl_lines: list[float] = []
        for (_season, _week), grp in pos_df.group_by(["season", "week"]):
            scores = [float(v) for v in grp["fp_sffm"].to_list()]
            start_lines.append(rank_threshold(scores, start_rank))
            repl_lines.append(rank_threshold(scores, repl_rank))
        thresholds[pos] = {
            "startable": round(_mean(start_lines), 2) if start_lines else _FALLBACK_STARTABLE[pos],
            "replacement": round(_mean(repl_lines), 2)
            if repl_lines
            else _FALLBACK_REPLACEMENT[pos],
        }
    return thresholds


def positional_medians(weekly: pl.DataFrame, scoring: dict[str, float]) -> dict[str, float]:
    """Median TD-share of fantasy points per position, across qualifying player-seasons."""
    medians: dict[str, float] = {}
    for pos in SKILL_POSITIONS:
        pos_df = weekly.filter(pl.col("position") == pos)
        if pos_df.is_empty():
            medians[pos] = 0.0
            continue
        shares: list[float] = []
        agg = pos_df.group_by("player_id").agg(
            [
                pl.col("fp_sffm").sum().alias("fp"),
                pl.col("passing_tds").sum().alias("ptd"),
                pl.col("rushing_tds").sum().alias("rtd"),
                pl.col("receiving_tds").sum().alias("rectd"),
            ]
        )
        for row in agg.iter_rows(named=True):
            fp = float(row["fp"] or 0.0)
            td_pts = (
                float(row["ptd"] or 0.0) * scoring.get("pass_td", 4.0)
                + float(row["rtd"] or 0.0) * scoring.get("rush_td", 6.0)
                + float(row["rectd"] or 0.0) * scoring.get("rec_td", 6.0)
            )
            share = td_dependence(td_pts, fp)
            if share is not None and fp >= 20.0:  # ignore noise from cameo lines
                shares.append(share)
        medians[pos] = round(_percentile(shares, 50), 3) if shares else 0.0
    return medians


def usage_coefficients(
    weekly: pl.DataFrame, scoring: dict[str, float]
) -> dict[str, dict[str, float]]:
    """Derive per-position points-per-target and points-per-carry from league weekly totals.

    Receiving fantasy points (receptions, yards, TDs under this league's scoring) are divided by
    total targets; rushing points by total carries. A crude but honest opportunity-value model —
    labelled UNCALIBRATED where surfaced.
    """
    coeffs: dict[str, dict[str, float]] = {}
    for pos in SKILL_POSITIONS:
        pos_df = weekly.filter(pl.col("position") == pos)
        if pos_df.is_empty():
            coeffs[pos] = {"targets": 0.0, "carries": 0.0}
            continue
        targets = float(pos_df["targets"].sum() or 0.0)
        carries = float(pos_df["carries"].sum() or 0.0)
        rec_fp = (
            float(pos_df["receptions"].sum() or 0.0) * scoring.get("rec", 1.0)
            + float(pos_df["receiving_yards"].sum() or 0.0) * scoring.get("rec_yd", 0.1)
            + float(pos_df["receiving_tds"].sum() or 0.0) * scoring.get("rec_td", 6.0)
        )
        rush_fp = float(pos_df["rushing_yards"].sum() or 0.0) * scoring.get(
            "rush_yd", 0.1
        ) + float(pos_df["rushing_tds"].sum() or 0.0) * scoring.get("rush_td", 6.0)
        pt = 1.7 if targets <= 0 else rec_fp / targets
        pc = 0.55 if carries <= 0 else rush_fp / carries
        coeffs[pos] = {"targets": round(pt, 4), "carries": round(pc, 4)}
    return coeffs


# ---------------------------------------------------------------------------
# Response model + orchestrator
# ---------------------------------------------------------------------------


@dataclass
class PlayerSabermetrics:
    """Full sabermetric suite for one player, matching the sabermetrics endpoint contract."""

    player_id: str
    name: str
    position: str
    seasons: list[int]
    consistency: dict
    td_dependence: dict
    opportunity_trend: dict
    age_curve: dict
    market_momentum: dict
    usage_quality: dict
    xfp: dict  # Slice B — UNCALIBRATED
    data_quality: str
    warnings: list[str] = field(default_factory=list)


def _profile_seasons() -> list[int]:
    cached = cached_weekly_seasons()
    return cached[-2:] if cached else []


def _resolve_gsis(player_id: str, player: dict) -> set[str]:
    ids = {str(player.get("gsis_id") or "")} - {""}
    try:
        id_map = load_id_map()
        matches = (
            id_map.filter(pl.col("sleeper_id").cast(pl.Int64, strict=False) == int(player_id))
            .select("gsis_id")
            .drop_nulls()
        )
        ids.update(str(row["gsis_id"]) for row in matches.iter_rows(named=True))
    except (ValueError, TypeError, pl.exceptions.PolarsError) as exc:
        log.debug("could not resolve gsis for %s: %s", player_id, exc)
    return ids


def _filter_player_weekly(weekly: pl.DataFrame, gsis_ids: set[str], name: str) -> pl.DataFrame:
    if weekly.is_empty():
        return weekly
    filters = []
    if gsis_ids:
        filters.append(pl.col("player_id").is_in(sorted(gsis_ids)))
    norm = _normalize_name(name)
    if norm:
        name_col = pl.col("player_display_name").map_elements(
            _normalize_name, return_dtype=pl.Utf8
        )
        filters.append(name_col.eq(norm))
    if not filters:
        return weekly.head(0)
    expr = filters[0]
    for item in filters[1:]:
        expr = expr | item
    return weekly.filter(expr).sort(["season", "week"])


def _latest_season_weekly(player_weekly: pl.DataFrame) -> tuple[int | None, pl.DataFrame]:
    if player_weekly.is_empty():
        return None, player_weekly
    latest = int(player_weekly["season"].max())  # type: ignore[arg-type]
    return latest, player_weekly.filter(pl.col("season") == latest)


def _snap_series(name: str, team: str, season: int) -> list[float]:
    try:
        snaps = load_snaps(seasons=[season])
    except Exception as exc:
        log.debug("snap load failed: %s", exc)
        return []
    if snaps.is_empty() or "player" not in snaps.columns:
        return []
    norm = _normalize_name(name)
    rows = snaps.filter(
        (pl.col("season") == season)
        & (pl.col("player").map_elements(_normalize_name, return_dtype=pl.Utf8).eq(norm))
    )
    if team and team != "FA" and "team" in rows.columns:
        team_rows = rows.filter(pl.col("team") == team)
        if not team_rows.is_empty():
            rows = team_rows
    rows = rows.sort("week")
    return [float(v) for v in rows["offense_pct"].to_list()]


def _usage_quality(season_df: pl.DataFrame, position: str, snaps: list[float]) -> dict:
    def _col_mean(col: str) -> float | None:
        if col not in season_df.columns:
            return None
        vals = [float(v) for v in season_df[col].to_list() if v is not None]
        return round(_mean(vals), 3) if vals else None

    targets = float(season_df["targets"].sum() or 0.0)
    carries = float(season_df["carries"].sum() or 0.0)
    explosive = float(season_df["receiving_40"].sum() or 0.0) + float(
        season_df["rushing_40"].sum() or 0.0
    )
    opps = targets + carries
    epa_cols = [
        c for c in ("receiving_epa", "rushing_epa", "passing_epa") if c in season_df.columns
    ]
    epa_total = sum(float(season_df[c].sum() or 0.0) for c in epa_cols)
    return {
        "wopr": _col_mean("wopr"),
        "target_share": _col_mean("target_share"),
        "air_yards_share": _col_mean("air_yards_share"),
        "racr": _col_mean("racr"),
        "epa_per_play": round(epa_total / opps, 3) if opps > 0 else None,
        "cpoe": _col_mean("passing_cpoe") if position == "QB" else None,
        "explosive_play_rate": round(explosive / opps, 3) if opps > 0 else None,
        "snap_share": round(_mean(snaps), 3) if snaps else None,
    }


def build_player_sabermetrics(
    player_id: str, seasons: list[int] | None = None
) -> PlayerSabermetrics:
    """Assemble the full player sabermetric suite from live nflverse + market data.

    Args:
        player_id: Sleeper player id.
        seasons: Seasons to analyse (defaults to the two most recent cached seasons).

    Returns:
        A populated :class:`PlayerSabermetrics`. Degraded metrics are None with a warning; the
        function never fabricates a value to fill a gap.
    """
    warnings: list[str] = []
    seasons = seasons or _profile_seasons()
    if not seasons:
        seasons = [DEFAULT_VALUE_SEASON]
        warnings.append("No cached weekly seasons; using configured value season.")

    with SleeperClient() as client:
        player = client.players().get(player_id, {})
    name = str(player.get("full_name") or player_id)
    position = str(player.get("position") or "")
    team = str(player.get("team") or "FA")

    scoring = load_scoring()
    weekly = score_weekly(seasons=seasons, scoring=scoring)
    gsis_ids = _resolve_gsis(player_id, player)
    player_weekly = _filter_player_weekly(weekly, gsis_ids, name)

    if player_weekly.is_empty():
        warnings.append("No weekly nflverse rows matched this player.")
        return PlayerSabermetrics(
            player_id=player_id,
            name=name,
            position=position,
            seasons=seasons,
            consistency={},
            td_dependence={},
            opportunity_trend={},
            age_curve={},
            market_momentum=_market_momentum(player_id),
            usage_quality={},
            xfp={},
            data_quality="no_data",
            warnings=warnings,
        )

    if not position:
        position = str(player_weekly["position"][-1] or "")

    latest_season, season_df = _latest_season_weekly(player_weekly)
    thresholds = weekly_positional_thresholds(weekly).get(
        position, {"startable": 0.0, "replacement": 0.0}
    )
    weekly_fp = [float(v) for v in season_df["fp_sffm"].to_list()]

    consistency = consistency_profile(
        weekly_fp, thresholds["startable"], thresholds["replacement"]
    )
    consistency["startable_line"] = thresholds["startable"]
    consistency["replacement_line"] = thresholds["replacement"]
    consistency["season"] = latest_season

    player_age = float(player.get("age") or 0.0) or None
    td_block = _td_block(season_df, position, weekly, scoring)
    opp_block = _opportunity_block(season_df, name, team, latest_season)
    age_block = _age_curve_block(player_weekly, position, player_age)
    usage = _usage_quality(season_df, position, _snap_series(name, team, latest_season or 0))
    xfp_block = _xfp_block(season_df, position, weekly, scoring, warnings)

    return PlayerSabermetrics(
        player_id=player_id,
        name=name,
        position=position,
        seasons=seasons,
        consistency=consistency,
        td_dependence=td_block,
        opportunity_trend=opp_block,
        age_curve=age_block,
        market_momentum=_market_momentum(player_id),
        usage_quality=usage,
        xfp=xfp_block,
        data_quality="ok",
        warnings=warnings,
    )


def _td_block(
    season_df: pl.DataFrame, position: str, weekly: pl.DataFrame, scoring: dict[str, float]
) -> dict:
    fp = float(season_df["fp_sffm"].sum() or 0.0)
    td_pts = (
        float(season_df["passing_tds"].sum() or 0.0) * scoring.get("pass_td", 4.0)
        + float(season_df["rushing_tds"].sum() or 0.0) * scoring.get("rush_td", 6.0)
        + float(season_df["receiving_tds"].sum() or 0.0) * scoring.get("rec_td", 6.0)
    )
    share = td_dependence(td_pts, fp)
    pos_median = positional_medians(weekly, scoring).get(position)
    return {
        "td_points": round(td_pts, 2),
        "total_fp": round(fp, 2),
        "td_share": share,
        "positional_median": pos_median,
        "vs_median": round(share - pos_median, 3)
        if share is not None and pos_median is not None
        else None,
    }


def _opportunity_block(
    season_df: pl.DataFrame, name: str, team: str, season: int | None
) -> dict:
    target_series = [float(v) for v in season_df["target_share"].to_list() if v is not None]
    carry_series = [float(v) for v in season_df["carries"].to_list() if v is not None]
    snap_series = _snap_series(name, team, season or 0)
    return {
        "snap_share_delta": opportunity_trend(snap_series),
        "target_share_delta": opportunity_trend(target_series),
        "carries_delta": opportunity_trend(carry_series),
        "window_weeks": 4,
    }


def _age_curve_block(
    player_weekly: pl.DataFrame, position: str, player_age: float | None
) -> dict:
    seasons = sorted(int(s) for s in player_weekly["season"].unique().to_list())
    if len(seasons) < 2:
        return {
            "residual": None,
            "expected_fpar": None,
            "actual_fpar": None,
            "note": "Needs two seasons of data to project the age arc.",
        }
    if player_age is None or player_age <= 0:
        return {
            "residual": None,
            "expected_fpar": None,
            "actual_fpar": None,
            "note": "Player age unavailable; cannot place FP on the age arc.",
        }
    prior_year, current_year = seasons[-2], seasons[-1]
    prior_fp = float(
        player_weekly.filter(pl.col("season") == prior_year)["fp_sffm"].sum() or 0.0
    )
    current_fp = float(
        player_weekly.filter(pl.col("season") == current_year)["fp_sffm"].sum() or 0.0
    )
    # Estimate the player's age during the prior season from current age and the season gap.
    prior_age = player_age - (CURRENT_LEAGUE_YEAR - prior_year)
    expected = age_curve_expected(prior_fp, prior_age, position)
    return {
        "residual": age_curve_residual(current_fp, expected),
        "expected_fpar": expected,
        "actual_fpar": round(current_fp, 2),
        "prior_season": prior_year,
        "current_season": current_year,
        "prior_age": round(prior_age, 1),
        "note": "Prior-season FP projected one year forward along the position age arc.",
    }


def _xfp_block(
    season_df: pl.DataFrame,
    position: str,
    weekly: pl.DataFrame,
    scoring: dict[str, float],
    warnings: list[str],
) -> dict:
    coeffs = usage_coefficients(weekly, scoring).get(position, {"targets": 0.0, "carries": 0.0})
    opps = {
        "targets": float(season_df["targets"].sum() or 0.0),
        "carries": float(season_df["carries"].sum() or 0.0),
    }
    xfp = expected_fp(opps, coeffs)
    actual = round(float(season_df["fp_sffm"].sum() or 0.0), 2)
    games = int(season_df.height)
    if games == 0:
        warnings.append("xFP has zero games of evidence.")
    return {
        "xfp": xfp,
        "actual_fp": actual,
        "residual": round(actual - xfp, 2),
        "coeffs": coeffs,
        "evidence_count": games,
        "label": "UNCALIBRATED — usage-value coefficients fit from league aggregates only.",
    }


def _market_momentum(player_id: str) -> dict:
    try:
        from sleeper_ffm.market.fantasycalc import fetch_full

        record = fetch_full().get(player_id, {})
    except Exception as exc:
        log.debug("market momentum unavailable for %s: %s", player_id, exc)
        record = {}
    return {
        "trend_30day": record.get("trend_30day"),
        "value": record.get("value"),
        "overall_rank": record.get("overall_rank"),
        "position_rank": record.get("position_rank"),
    }
