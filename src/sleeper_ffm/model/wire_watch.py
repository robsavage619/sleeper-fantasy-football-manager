"""Wire early-warning — emerging opportunity before the waiver herd notices.

Snap share is the leading indicator that shows up before the box score does: a back
whose snaps jumped from 30% to 65% over the last three weeks is about to matter, usually
a week ahead of the points that make everyone else bid. This module finds those risers
and cross-references league ownership so it only surfaces players you can actually add.

In season it's a live get-ahead-of-the-wire feed; in the off-season it surfaces the
late-season snap-share risers who ended the year trending up and are still available — the
stashes worth making now. The rising-role signal is the same either way.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

import polars as pl

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.config import DEFAULT_VALUE_SEASON
from sleeper_ffm.model.valuation import SKILL_POSITIONS
from sleeper_ffm.nflverse.loader import load_id_map, load_snaps

log = logging.getLogger(__name__)

# How many trailing weeks count as "recent" for the trend.
_RECENT_N: int = 3
# A snap-share jump this large (fraction of team snaps) is a real role change.
_MIN_DELTA: float = 0.15
# Recent snap share must clear this to be worth a claim (a real role, not a blip).
_MIN_RECENT_PCT: float = 0.35


@dataclass
class WireAlert:
    """One emerging-opportunity player."""

    player_id: str
    name: str
    position: str
    team: str
    recent_pct: float  # mean offensive snap share over the last _RECENT_N weeks
    prior_pct: float  # mean over the earlier weeks
    delta: float  # recent - prior; the size of the role change
    available: bool  # not rostered in this league
    note: str = ""


@dataclass
class WireWatch:
    """Ranked wire early-warning board."""

    season: int
    recent_n: int
    alerts: list[WireAlert]  # available risers, largest jump first
    warnings: list[str] = field(default_factory=list)


def snap_trend(
    weeks: list[tuple[int, float]], recent_n: int = _RECENT_N
) -> tuple[float, float, float] | None:
    """Return ``(recent_pct, prior_pct, delta)`` from a player's weekly snap shares. Pure.

    Args:
        weeks: ``[(week, offense_pct), ...]`` for one player.
        recent_n: Trailing weeks treated as "recent".

    Returns:
        The trend triple, or None if there aren't enough weeks to form a prior + recent split.
    """
    if len(weeks) < recent_n + 1:
        return None
    ordered = [pct for _, pct in sorted(weeks)]
    recent = ordered[-recent_n:]
    prior = ordered[:-recent_n]
    recent_avg = statistics.mean(recent)
    prior_avg = statistics.mean(prior)
    return round(recent_avg, 3), round(prior_avg, 3), round(recent_avg - prior_avg, 3)


def is_riser(
    recent_pct: float,
    delta: float,
    min_recent: float = _MIN_RECENT_PCT,
    min_delta: float = _MIN_DELTA,
) -> bool:
    """Whether a trend clears both the role-size and role-change bars. Pure."""
    return recent_pct >= min_recent and delta >= min_delta


@ttl_cache()
def build_wire_watch(season: int | None = None, my_roster_id: int | None = None) -> WireWatch:
    """Build the wire early-warning board.

    Returns:
        A :class:`WireWatch` of available snap-share risers, largest jump first.
    """
    from sleeper_ffm.sleeper.client import SleeperClient

    season = season or DEFAULT_VALUE_SEASON
    warnings: list[str] = []

    snaps = load_snaps(seasons=[season])
    needed = {"pfr_player_id", "offense_pct", "position", "week", "season", "player", "team"}
    if snaps.is_empty() or not needed.issubset(snaps.columns):
        warnings.append(f"Snap data unavailable for {season}; wire watch empty.")
        return WireWatch(season, _RECENT_N, [], warnings)

    reg = snaps.filter(
        (pl.col("season") == season) & (pl.col("position").is_in(list(SKILL_POSITIONS)))
    )
    if "game_type" in reg.columns:
        reg = reg.filter(pl.col("game_type") == "REG")

    per_player: dict[str, dict] = {}
    for r in reg.iter_rows(named=True):
        pid = r.get("pfr_player_id")
        pct = r.get("offense_pct")
        if not pid or pct is None:
            continue
        rec = per_player.setdefault(
            pid,
            {
                "name": r.get("player") or pid,
                "position": r["position"],
                "team": r.get("team") or "FA",
                "weeks": [],
            },
        )
        rec["weeks"].append((int(r["week"]), float(pct)))

    pfr_to_sid = _pfr_to_sleeper()
    with SleeperClient() as c:
        rosters = c.rosters()
    owned: set[str] = set()
    for r in rosters:
        owned.update(r.players or [])

    alerts: list[WireAlert] = []
    for pfr, rec in per_player.items():
        trend = snap_trend(rec["weeks"])
        if trend is None:
            continue
        recent_pct, prior_pct, delta = trend
        if not is_riser(recent_pct, delta):
            continue
        sid = pfr_to_sid.get(pfr)
        available = sid is None or sid not in owned
        alerts.append(
            WireAlert(
                player_id=sid or f"pfr:{pfr}",
                name=rec["name"],
                position=rec["position"],
                team=rec["team"],
                recent_pct=recent_pct,
                prior_pct=prior_pct,
                delta=delta,
                available=available,
                note=f"snap share {prior_pct:.0%} → {recent_pct:.0%} (+{delta:.0%})",
            )
        )

    # Available risers first, then by the size of the jump.
    alerts.sort(key=lambda a: (a.available, a.delta), reverse=True)
    return WireWatch(season=season, recent_n=_RECENT_N, alerts=alerts, warnings=warnings)


def _pfr_to_sleeper() -> dict[str, str]:
    """Return ``{pfr_id: sleeper_id_str}`` from the crosswalk."""
    id_map = load_id_map()
    if "pfr_id" not in id_map.columns or "sleeper_id" not in id_map.columns:
        return {}
    slim = (
        id_map.select(["pfr_id", "sleeper_id"])
        .filter(pl.col("pfr_id").is_not_null() & pl.col("sleeper_id").is_not_null())
        .with_columns(
            pl.col("sleeper_id").cast(pl.Int64, strict=False).cast(pl.Utf8).alias("sleeper_id_str")
        )
        .filter(pl.col("sleeper_id_str").is_not_null())
    )
    return {r["pfr_id"]: r["sleeper_id_str"] for r in slim.iter_rows(named=True)}
