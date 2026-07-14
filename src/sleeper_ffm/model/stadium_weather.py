"""Stadium & weather performance splits — environment context for start/sit.

Joins each historical player-week (scored under this league's rules) to its game's
venue and conditions from the nflverse schedule (roof, temperature, wind, stadium),
then aggregates how each player has actually performed in controlled vs exposed
environments, in cold, in wind, and in specific stadiums.

The point is decision support, not narrative: when the optimizer is on the fence
between two flex plays and one is headed to a 20-mph wind tunnel he has historically
faded in, that split breaks the tie.

Weather realism caveats:
    * ``temp`` / ``wind`` are only populated for outdoor/open games; dome and closed
      roofs are treated as controlled (no cold/wind effect) regardless of nulls.
    * Splits are descriptive of past games, not forecasts. Upcoming-game venue and
      roof are known from the schedule; live temp/wind forecasts are a future add.
    * Per-stadium samples are thin — a split needs ``_MIN_STADIUM_GAMES`` games before
      it is surfaced, and even then reads as a lean, not a law.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

import polars as pl

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.config import DEFAULT_VALUE_SEASON
from sleeper_ffm.model.valuation import score_weekly
from sleeper_ffm.nflverse.loader import load_id_map, load_schedules

log = logging.getLogger(__name__)

# Roofs where weather cannot touch the game.
_CONTROLLED_ROOFS: frozenset[str] = frozenset({"dome", "closed"})
# Outdoor thermometer/anemometer thresholds for the cold / windy buckets.
_COLD_F: float = 40.0
_WINDY_MPH: float = 15.0
# A split needs at least this many games before it is trustworthy enough to surface.
_MIN_BUCKET_GAMES: int = 3
_MIN_STADIUM_GAMES: int = 3
# |delta| beyond this (FP/game) is flagged as a real environmental lean.
_MATERIAL_DELTA: float = 1.5


@dataclass
class EnvSplit:
    """One environment bucket's sample for a player."""

    bucket: str  # "controlled" | "exposed" | "cold" | "windy"
    games: int
    avg_fp: float
    delta: float  # avg_fp minus the player's overall avg_fp


@dataclass
class StadiumSplit:
    """A player's history in one specific stadium."""

    stadium: str
    games: int
    avg_fp: float
    delta: float


@dataclass
class PlayerEnvironmentProfile:
    """How a player has performed across venues and weather."""

    player_id: str
    name: str
    position: str
    total_games: int
    overall_avg_fp: float
    splits: dict[str, EnvSplit]  # keyed by bucket
    stadiums: list[StadiumSplit]  # material samples, largest |delta| first
    flags: list[str] = field(default_factory=list)


def classify_env(roof: str | None, temp: float | None, wind: float | None) -> set[str]:
    """Return the environment buckets a game falls into.

    Args:
        roof: nflverse roof value (``dome``/``closed``/``outdoors``/``open``/None).
        temp: Game-time temperature (°F) — only meaningful outdoors.
        wind: Game-time wind (mph) — only meaningful outdoors.

    Returns:
        A set drawn from ``{"controlled", "exposed", "cold", "windy"}``. Controlled
        games never carry cold/windy; exposed games add them when the reading clears
        the threshold.
    """
    roof_norm = (roof or "").strip().lower()
    if roof_norm in _CONTROLLED_ROOFS:
        return {"controlled"}
    buckets = {"exposed"}
    if temp is not None and temp <= _COLD_F:
        buckets.add("cold")
    if wind is not None and wind >= _WINDY_MPH:
        buckets.add("windy")
    return buckets


def summarize_player(
    player_id: str,
    name: str,
    position: str,
    games: list[dict],
) -> PlayerEnvironmentProfile:
    """Aggregate one player's environment splits from their scored game rows.

    Args:
        player_id: Sleeper player id.
        name: Display name.
        position: Position.
        games: List of ``{fp, roof, temp, wind, stadium}`` dicts, one per game.

    Returns:
        A :class:`PlayerEnvironmentProfile`. Pure — no I/O.
    """
    fps = [g["fp"] for g in games]
    overall = statistics.mean(fps) if fps else 0.0

    bucket_fps: dict[str, list[float]] = {}
    stadium_fps: dict[str, list[float]] = {}
    for g in games:
        for bucket in classify_env(g.get("roof"), g.get("temp"), g.get("wind")):
            bucket_fps.setdefault(bucket, []).append(g["fp"])
        stadium = (g.get("stadium") or "").strip()
        if stadium:
            stadium_fps.setdefault(stadium, []).append(g["fp"])

    splits: dict[str, EnvSplit] = {}
    for bucket, vals in bucket_fps.items():
        if len(vals) < _MIN_BUCKET_GAMES:
            continue
        avg = round(statistics.mean(vals), 1)
        splits[bucket] = EnvSplit(
            bucket=bucket,
            games=len(vals),
            avg_fp=avg,
            delta=round(avg - overall, 1),
        )

    stadiums = [
        StadiumSplit(
            stadium=stadium,
            games=len(vals),
            avg_fp=round(statistics.mean(vals), 1),
            delta=round(statistics.mean(vals) - overall, 1),
        )
        for stadium, vals in stadium_fps.items()
        if len(vals) >= _MIN_STADIUM_GAMES
    ]
    stadiums.sort(key=lambda s: abs(s.delta), reverse=True)

    flags: list[str] = []
    for bucket in ("cold", "windy", "exposed"):
        split = splits.get(bucket)
        if split and split.delta <= -_MATERIAL_DELTA:
            flags.append(f"{split.delta:+.1f} FP/g in {bucket} games ({split.games})")
    ctrl, exp = splits.get("controlled"), splits.get("exposed")
    if ctrl and exp and ctrl.delta - exp.delta >= _MATERIAL_DELTA:
        flags.append(f"dome-boosted: {ctrl.delta - exp.delta:+.1f} FP/g indoors vs out")

    return PlayerEnvironmentProfile(
        player_id=player_id,
        name=name,
        position=position,
        total_games=len(fps),
        overall_avg_fp=round(overall, 1),
        splits=splits,
        stadiums=stadiums,
        flags=flags,
    )


def _schedule_env_long(seasons: list[int]) -> pl.DataFrame:
    """Return one row per (season, week, team) with that game's environment."""
    sched = load_schedules(seasons=seasons)
    keep = ["season", "week", "home_team", "away_team", "roof", "temp", "wind", "stadium"]
    have = [c for c in keep if c in sched.columns]
    sched = sched.select(have)
    home = sched.rename({"home_team": "team"}).drop("away_team", strict=False)
    away = sched.rename({"away_team": "team"}).drop("home_team", strict=False)
    return pl.concat([home, away], how="diagonal")


@ttl_cache()
def build_environment_splits(
    seasons: tuple[int, ...] | None = None,
) -> dict[str, PlayerEnvironmentProfile]:
    """Compute stadium/weather splits for every scored player in one pass.

    Args:
        seasons: Seasons of history to aggregate (default: the latest completed season
            and the two prior, for sample depth). ``load_weekly`` now concats across the
            2023/2024 schema boundary, so spanning eras is safe.

    Returns:
        ``{sleeper_id: PlayerEnvironmentProfile}``. Empty if data is unavailable.
    """
    season_list = (
        list(seasons)
        if seasons
        else [DEFAULT_VALUE_SEASON - 2, DEFAULT_VALUE_SEASON - 1, DEFAULT_VALUE_SEASON]
    )
    scored = score_weekly(seasons=season_list)
    if scored.is_empty():
        log.warning("stadium_weather: no scored weekly data for %s", seasons)
        return {}

    env = _schedule_env_long(season_list)
    joined = scored.join(
        env,
        left_on=["season", "week", "recent_team"],
        right_on=["season", "week", "team"],
        how="inner",
    )
    if joined.is_empty():
        log.warning("stadium_weather: weekly↔schedule join produced no rows")
        return {}

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
    joined = joined.join(id_slim, left_on="player_id", right_on="gsis_id", how="left")

    by_player: dict[str, dict] = {}
    for row in joined.iter_rows(named=True):
        sid = row.get("sleeper_id_str")
        if not sid:
            continue
        rec = by_player.setdefault(
            sid,
            {
                "name": row.get("player_display_name") or "?",
                "position": row.get("position") or "?",
                "games": [],
            },
        )
        rec["games"].append(
            {
                "fp": float(row["fp_sffm"] or 0.0),
                "roof": row.get("roof"),
                "temp": row.get("temp"),
                "wind": row.get("wind"),
                "stadium": row.get("stadium"),
            }
        )

    profiles = {
        sid: summarize_player(sid, rec["name"], rec["position"], rec["games"])
        for sid, rec in by_player.items()
    }
    log.info("stadium_weather: built environment profiles for %d players", len(profiles))
    return profiles
