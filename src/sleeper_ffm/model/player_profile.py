"""Player intelligence profiles for drawer views."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from numbers import Real

import polars as pl

from sleeper_ffm.config import DEFAULT_VALUE_SEASON, cached_weekly_seasons
from sleeper_ffm.model.dynasty import PlayerAsset, value_pick, value_player_breakdown
from sleeper_ffm.model.valuation import (
    _normalize_name,
    _rookie_fpar,
    build_player_assets,
    score_weekly,
)
from sleeper_ffm.nflverse.loader import load_depth_charts, load_id_map, load_injuries, load_snaps
from sleeper_ffm.scoring.engine import load_scoring
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)


@dataclass
class PlayerProfile:
    """Historical player profile shown in the frontend drawer."""

    player_id: str
    identity: dict
    value: dict
    fantasy_summary: dict
    season_summaries: list[dict]
    weekly: list[dict]
    usage: dict
    injuries: list[dict]
    depth: dict | None
    data_quality: str
    warnings: list[str] = field(default_factory=list)


def build_player_profile(player_id: str, seasons: list[int] | None = None) -> PlayerProfile:
    """Build a historical profile for one Sleeper player ID."""
    with SleeperClient() as client:
        sleeper_players = client.players()

    player = sleeper_players.get(player_id, {})
    identity = _identity(player_id, player)
    seasons = seasons or _profile_seasons()
    warnings: list[str] = []
    if not seasons:
        seasons = [DEFAULT_VALUE_SEASON]
        warnings.append("No cached weekly seasons found; using configured value season.")

    gsis_ids = _gsis_ids(player_id, player)
    scoring = load_scoring()
    weekly = score_weekly(seasons=seasons, scoring=scoring)
    player_weekly = _filter_player_weekly(weekly, gsis_ids, identity)
    if player_weekly.is_empty():
        warnings.append("No nflverse weekly stat history found for this player.")

    weekly_rows = _weekly_rows(player_weekly)
    season_summaries = _season_summaries(player_weekly)
    fantasy_summary = _fantasy_summary(weekly_rows, season_summaries)
    value = _value_snapshot(player_id, identity, player, sleeper_players, warnings)
    usage = _usage_snapshot(player_weekly, identity, seasons, warnings)
    injuries = _injury_rows(gsis_ids, identity, seasons, warnings)
    depth = _depth_snapshot(gsis_ids, identity, seasons, warnings)

    data_quality = "FULL" if not warnings else "DEGRADED"
    return PlayerProfile(
        player_id=player_id,
        identity=identity,
        value=value,
        fantasy_summary=fantasy_summary,
        season_summaries=season_summaries,
        weekly=weekly_rows[-24:],
        usage=usage,
        injuries=injuries[-20:],
        depth=depth,
        data_quality=data_quality,
        warnings=warnings,
    )


def _profile_seasons() -> list[int]:
    cached = cached_weekly_seasons()
    if not cached:
        return []
    return cached[-3:]


def _identity(player_id: str, player: dict) -> dict:
    return {
        "player_id": player_id,
        "name": player.get("full_name") or player.get("search_full_name") or f"Player {player_id}",
        "position": player.get("position") or "",
        "team": player.get("team") or "FA",
        "age": float(player.get("age") or 0),
        "years_exp": player.get("years_exp"),
        "status": player.get("status") or "",
        "injury_status": player.get("injury_status") or "",
        "search_rank": player.get("search_rank"),
        "gsis_id": player.get("gsis_id") or "",
    }


def _gsis_ids(player_id: str, player: dict) -> set[str]:
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
        log.debug("could not resolve gsis_id for %s: %s", player_id, exc)
    return ids


def _filter_player_weekly(weekly: pl.DataFrame, gsis_ids: set[str], identity: dict) -> pl.DataFrame:
    if weekly.is_empty():
        return weekly
    filters = []
    if gsis_ids:
        filters.append(pl.col("player_id").is_in(sorted(gsis_ids)))
    name = _normalize_name(str(identity["name"]))
    if name:
        filters.append(
            pl.col("player_display_name")
            .map_elements(_normalize_name, return_dtype=pl.Utf8)
            .eq(name)
        )
    if not filters:
        return weekly.head(0)
    expr = filters[0]
    for item in filters[1:]:
        expr = expr | item
    return weekly.filter(expr).sort(["season", "week"])


def _weekly_rows(player_weekly: pl.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for row in player_weekly.iter_rows(named=True):
        passing_td = _float(row.get("passing_tds"))
        rushing_td = _float(row.get("rushing_tds"))
        receiving_td = _float(row.get("receiving_tds"))
        rows.append(
            {
                "season": int(_float(row.get("season"))),
                "week": int(_float(row.get("week"))),
                "team": row.get("recent_team") or "",
                "opponent": row.get("opponent_team") or "",
                "fantasy_points": round(_float(row.get("fp_sffm")), 2),
                "targets": int(_float(row.get("targets"))),
                "carries": int(_float(row.get("carries"))),
                "receptions": int(_float(row.get("receptions"))),
                "passing_yards": round(_float(row.get("passing_yards")), 1),
                "rushing_yards": round(_float(row.get("rushing_yards")), 1),
                "receiving_yards": round(_float(row.get("receiving_yards")), 1),
                "touchdowns": int(passing_td + rushing_td + receiving_td),
            }
        )
    return rows


def _season_summaries(player_weekly: pl.DataFrame) -> list[dict]:
    if player_weekly.is_empty():
        return []
    grouped = (
        player_weekly.group_by("season")
        .agg(
            [
                pl.len().alias("games"),
                pl.col("fp_sffm").sum().alias("fantasy_points"),
                pl.col("fp_sffm").mean().alias("points_per_game"),
                pl.col("targets").sum().alias("targets"),
                pl.col("carries").sum().alias("carries"),
                pl.col("receptions").sum().alias("receptions"),
                pl.col("passing_yards").sum().alias("passing_yards"),
                pl.col("rushing_yards").sum().alias("rushing_yards"),
                pl.col("receiving_yards").sum().alias("receiving_yards"),
                pl.col("target_share").mean().alias("target_share"),
                pl.col("air_yards_share").mean().alias("air_yards_share"),
            ]
        )
        .sort("season")
    )
    return [
        {
            "season": int(row["season"]),
            "games": int(row["games"]),
            "fantasy_points": round(_float(row["fantasy_points"]), 2),
            "points_per_game": round(_float(row["points_per_game"]), 2),
            "targets": int(_float(row["targets"])),
            "carries": int(_float(row["carries"])),
            "receptions": int(_float(row["receptions"])),
            "passing_yards": round(_float(row["passing_yards"]), 1),
            "rushing_yards": round(_float(row["rushing_yards"]), 1),
            "receiving_yards": round(_float(row["receiving_yards"]), 1),
            "target_share": round(_float(row["target_share"]) * 100, 1),
            "air_yards_share": round(_float(row["air_yards_share"]) * 100, 1),
        }
        for row in grouped.iter_rows(named=True)
    ]


def _fantasy_summary(weekly_rows: list[dict], season_summaries: list[dict]) -> dict:
    if not weekly_rows:
        return {
            "games": 0,
            "fantasy_points": 0.0,
            "points_per_game": 0.0,
            "best_week": None,
            "worst_week": None,
            "boom_weeks": 0,
            "bust_weeks": 0,
        }
    total = sum(row["fantasy_points"] for row in weekly_rows)
    best = max(weekly_rows, key=lambda row: row["fantasy_points"])
    worst = min(weekly_rows, key=lambda row: row["fantasy_points"])
    return {
        "games": len(weekly_rows),
        "seasons": len(season_summaries),
        "fantasy_points": round(total, 2),
        "points_per_game": round(total / len(weekly_rows), 2),
        "best_week": best,
        "worst_week": worst,
        "boom_weeks": sum(1 for row in weekly_rows if row["fantasy_points"] >= 20),
        "bust_weeks": sum(1 for row in weekly_rows if row["fantasy_points"] < 6),
    }


def _value_snapshot(
    player_id: str,
    identity: dict,
    player: dict,
    sleeper_players: dict[str, dict],
    warnings: list[str],
) -> dict:
    try:
        assets = build_player_assets(
            seasons=[DEFAULT_VALUE_SEASON], sleeper_players=sleeper_players
        )
        asset = next((item for item in assets if item.player_id == player_id), None)
    except Exception as exc:
        log.warning("player profile value build failed for %s: %s", player_id, exc)
        asset = None
        warnings.append("Dynasty value could not be computed from nflverse history.")

    if asset is None:
        search_rank = player.get("search_rank")
        fpar = _rookie_fpar(int(search_rank)) if search_rank is not None else 0.0
        asset = PlayerAsset(
            player_id=player_id,
            name=str(identity["name"]),
            position=str(identity["position"]),
            age=_float(identity["age"]),
            current_fpar=fpar,
            team=str(identity["team"]),
            is_taxi=True,
        )

    breakdown = value_player_breakdown(asset)
    dynasty_value = breakdown.value
    return {
        "current_fpar": asset.current_fpar,
        "dynasty_value": dynasty_value,
        "age_curve_adjustment": breakdown.age_curve_adjustment,
        "career_phase": breakdown.career_phase,
        "pick_equivalent": _pick_equivalent(dynasty_value),
        "age_curve": _age_curve_note(asset),
        "valuation_season": DEFAULT_VALUE_SEASON,
    }


def _usage_snapshot(
    player_weekly: pl.DataFrame,
    identity: dict,
    seasons: list[int],
    warnings: list[str],
) -> dict:
    rows = _weekly_rows(player_weekly)
    latest = rows[-5:]
    usage = {
        "recent_targets_per_game": _avg([row["targets"] for row in latest]),
        "recent_carries_per_game": _avg([row["carries"] for row in latest]),
        "recent_touches_per_game": _avg([row["targets"] + row["carries"] for row in latest]),
        "recent_points_per_game": _avg([row["fantasy_points"] for row in latest]),
        "avg_snap_pct": None,
        "recent_snap_pct": None,
    }

    try:
        snaps = load_snaps(seasons=seasons)
        snap_rows = _filter_snap_rows(snaps, identity)
        if not snap_rows.is_empty():
            usage["avg_snap_pct"] = round(_float(snap_rows["offense_pct"].mean()) * 100, 1)
            latest_snap = snap_rows.sort(["season", "week"]).tail(5)
            usage["recent_snap_pct"] = round(_float(latest_snap["offense_pct"].mean()) * 100, 1)
    except Exception as exc:
        log.warning("snap data unavailable for %s: %s", identity["name"], exc)
        warnings.append("Snap-count data unavailable.")
    return usage


def _filter_snap_rows(snaps: pl.DataFrame, identity: dict) -> pl.DataFrame:
    if snaps.is_empty() or "player" not in snaps.columns:
        return snaps
    name = _normalize_name(str(identity["name"]))
    team = str(identity["team"])
    rows = snaps.filter(
        pl.col("player").map_elements(_normalize_name, return_dtype=pl.Utf8).eq(name)
    )
    if team and team != "FA" and "team" in rows.columns:
        team_rows = rows.filter(pl.col("team") == team)
        if not team_rows.is_empty():
            return team_rows
    return rows


def _injury_rows(
    gsis_ids: set[str],
    identity: dict,
    seasons: list[int],
    warnings: list[str],
) -> list[dict]:
    try:
        injuries = load_injuries(seasons=seasons)
    except Exception as exc:
        log.warning("injury data unavailable for %s: %s", identity["name"], exc)
        warnings.append("Injury history unavailable.")
        return []
    if injuries.is_empty():
        return []
    rows = _filter_gsis_or_name(injuries, gsis_ids, identity, name_col="full_name")
    status_counter = Counter(
        str(row["report_status"] or "Unknown") for row in rows.iter_rows(named=True)
    )
    output = [
        {
            "season": int(_float(row.get("season"))),
            "week": int(_float(row.get("week"))),
            "team": row.get("team") or "",
            "injury": row.get("report_primary_injury") or row.get("practice_primary_injury") or "",
            "status": row.get("report_status") or row.get("practice_status") or "",
        }
        for row in rows.sort(["season", "week"]).iter_rows(named=True)
    ]
    if output:
        output.append(
            {
                "season": 0,
                "week": 0,
                "team": "",
                "injury": "summary",
                "status": ", ".join(f"{label}: {count}" for label, count in status_counter.items()),
            }
        )
    return output


def _depth_snapshot(
    gsis_ids: set[str],
    identity: dict,
    seasons: list[int],
    warnings: list[str],
) -> dict | None:
    try:
        depth = load_depth_charts(seasons=seasons)
    except Exception as exc:
        log.warning("depth chart data unavailable for %s: %s", identity["name"], exc)
        warnings.append("Depth-chart history unavailable.")
        return None
    if depth.is_empty():
        return None
    rows = _filter_gsis_or_name(depth, gsis_ids, identity, name_col="full_name")
    if rows.is_empty():
        return None
    latest = rows.sort(["season", "week"]).tail(1).to_dicts()[0]
    return {
        "season": int(_float(latest.get("season"))),
        "week": int(_float(latest.get("week"))),
        "team": latest.get("club_code") or "",
        "depth_team": latest.get("depth_team") or "",
        "depth_position": latest.get("depth_position") or latest.get("position") or "",
        "formation": latest.get("formation") or "",
    }


def _filter_gsis_or_name(
    frame: pl.DataFrame,
    gsis_ids: set[str],
    identity: dict,
    name_col: str,
) -> pl.DataFrame:
    filters = []
    if gsis_ids and "gsis_id" in frame.columns:
        filters.append(pl.col("gsis_id").is_in(sorted(gsis_ids)))
    if name_col in frame.columns:
        name = _normalize_name(str(identity["name"]))
        filters.append(
            pl.col(name_col).map_elements(_normalize_name, return_dtype=pl.Utf8).eq(name)
        )
    if not filters:
        return frame.head(0)
    expr = filters[0]
    for item in filters[1:]:
        expr = expr | item
    return frame.filter(expr)


def _pick_equivalent(value: float) -> str:
    from sleeper_ffm.model.dynasty import PickAsset

    picks = [
        ("1st", value_pick(PickAsset("2026", 1, 0, 0))),
        ("2nd", value_pick(PickAsset("2026", 2, 0, 0))),
        ("3rd", value_pick(PickAsset("2026", 3, 0, 0))),
        ("4th", value_pick(PickAsset("2026", 4, 0, 0))),
    ]
    label, _ = min(picks, key=lambda item: abs(item[1] - value))
    return label


def _age_curve_note(asset: PlayerAsset) -> str:
    if asset.position == "RB" and asset.age >= 27:
        return "RB age cliff risk is active."
    if asset.position in {"WR", "TE"} and asset.age <= 25:
        return "Still inside prime development window."
    if asset.position == "QB" and asset.age <= 32:
        return "QB shelf life remains favorable."
    return "Neutral age-curve read."


def _avg(values: list[float | int]) -> float:
    if not values:
        return 0.0
    return round(sum(float(value) for value in values) / len(values), 2)


def _float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Real):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0
