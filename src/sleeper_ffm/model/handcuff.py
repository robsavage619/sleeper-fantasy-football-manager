"""Handcuff & leverage map — contingent value across the roster.

Two questions this answers that raw valuation cannot:

    1. **Is my roster's contingent value secured?** For each of my starters, who is the
       direct backup on the NFL depth chart, and do I own them? An unrostered backup
       behind my RB1 is an exposed injury cliff; owning him is cheap insurance that also
       denies a rival the leverage.

    2. **Where can I create leverage?** A rival contender's league-winner RB whose
       handcuff is sitting in free agency is a stash worth making — grab the one player
       that team cannot afford to lose, and you own a piece of their season.

Depth order comes from the latest nflverse depth-chart snapshot (``pos_rank`` within
``pos_abb`` per team); ownership comes from the live league rosters. Both are facts, so
the links are exact — the judgment is which exposures are worth insuring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import polars as pl

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.config import DEFAULT_VALUE_SEASON, MY_ROSTER_ID
from sleeper_ffm.model.valuation import SKILL_POSITIONS
from sleeper_ffm.nflverse.loader import load_depth_charts, load_id_map

log = logging.getLogger(__name__)


@dataclass
class HandcuffLink:
    """A starter and their direct backup, with ownership status."""

    starter_id: str
    starter_name: str
    position: str
    team: str
    backup_id: str | None
    backup_name: str | None
    backup_owner: str  # "me" | "roster:<id>" | "free_agent" | "unknown"
    status: str  # "SECURED" | "EXPOSED" | "NO_BACKUP"


@dataclass
class LeverageStash:
    """An available backup behind a rival's valuable starter — a stash worth making."""

    backup_id: str
    backup_name: str
    position: str
    team: str
    starter_name: str
    starter_owner: str  # "roster:<id>"


@dataclass
class HandcuffMap:
    """My roster's contingent-value picture plus league leverage plays."""

    season: int
    my_links: list[HandcuffLink]  # my starters and whether their backup is secured
    exposed: list[HandcuffLink]  # subset: my starters with an unowned backup
    leverage_stashes: list[LeverageStash]  # available backups behind rivals' starters
    warnings: list[str] = field(default_factory=list)


def order_depth(rows: list[dict]) -> dict[tuple[str, str], list[str]]:
    """Order players into ``{(team, position): [sid_by_rank, ...]}``. Pure.

    Args:
        rows: ``[{team, position, rank, sid}, ...]``; lower rank = higher on the chart.
    """
    grouped: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for r in rows:
        if not r.get("sid"):
            continue
        grouped.setdefault((r["team"], r["position"]), []).append((r["rank"], r["sid"]))
    return {key: [sid for _, sid in sorted(vals)] for key, vals in grouped.items()}


def backup_of(
    order: dict[tuple[str, str], list[str]], team: str, pos: str, starter: str
) -> str | None:
    """Return the player directly behind ``starter`` on the depth chart, or None."""
    chain = order.get((team, pos), [])
    if starter not in chain:
        return None
    idx = chain.index(starter)
    return chain[idx + 1] if idx + 1 < len(chain) else None


def classify_status(backup_id: str | None, backup_owner: str) -> str:
    """SECURED (I own the backup), EXPOSED (someone else / nobody), or NO_BACKUP."""
    if backup_id is None:
        return "NO_BACKUP"
    return "SECURED" if backup_owner == "me" else "EXPOSED"


def _latest_depth_rows(season: int) -> list[dict]:
    """Return the most-recent depth-chart snapshot per team as plain rows."""
    dc = load_depth_charts(seasons=[season])
    needed = {"team", "pos_abb", "pos_rank", "gsis_id", "dt"}
    if dc.is_empty() or not needed.issubset(dc.columns):
        return []
    latest = dc.group_by("team").agg(pl.col("dt").max().alias("_mdt"))
    dc = dc.join(latest, on="team").filter(pl.col("dt") == pl.col("_mdt"))

    id_map = load_id_map()
    id_slim = (
        id_map.select(["gsis_id", "sleeper_id"])
        .filter(pl.col("gsis_id").is_not_null() & pl.col("sleeper_id").is_not_null())
        .with_columns(
            pl.col("sleeper_id").cast(pl.Int64, strict=False).cast(pl.Utf8).alias("sleeper_id_str")
        )
        .select(["gsis_id", "sleeper_id_str"])
    )
    dc = dc.join(id_slim, on="gsis_id", how="left")

    rows: list[dict] = []
    for r in dc.iter_rows(named=True):
        pos = r.get("pos_abb")
        if pos not in SKILL_POSITIONS or r.get("pos_rank") is None:
            continue
        rows.append(
            {
                "team": r.get("team"),
                "position": pos,
                "rank": int(r["pos_rank"]),
                "sid": r.get("sleeper_id_str"),
                "name": r.get("player_name") or r.get("sleeper_id_str") or "?",
            }
        )
    return rows


@ttl_cache()
def build_handcuff_map(my_roster_id: int = MY_ROSTER_ID) -> HandcuffMap:
    """Build the handcuff/leverage map for my roster.

    Returns:
        A :class:`HandcuffMap`. Degrades gracefully when depth-chart data is missing.
    """
    from sleeper_ffm.model.dynasty import value_player
    from sleeper_ffm.model.valuation import build_player_assets
    from sleeper_ffm.sleeper.client import SleeperClient

    warnings: list[str] = []
    rows = _latest_depth_rows(DEFAULT_VALUE_SEASON)
    if not rows:
        warnings.append("Depth-chart data unavailable; handcuff map empty.")
        return HandcuffMap(DEFAULT_VALUE_SEASON, [], [], [], warnings)

    order = order_depth(rows)
    name_by_sid = {r["sid"]: r["name"] for r in rows if r["sid"]}

    with SleeperClient() as c:
        rosters = c.rosters()
        players = c.players()
    owner_of: dict[str, int] = {}
    for r in rosters:
        for pid in r.players or []:
            owner_of[pid] = r.roster_id

    def _owner_label(sid: str | None) -> str:
        if sid is None or sid not in owner_of:
            return "free_agent"
        rid = owner_of[sid]
        return "me" if rid == my_roster_id else f"roster:{rid}"

    try:
        assets = build_player_assets(seasons=[DEFAULT_VALUE_SEASON], sleeper_players=players)
        value_by_sid = {a.player_id: value_player(a) for a in assets}
    except Exception as exc:
        log.warning("handcuff: values unavailable: %s", exc)
        value_by_sid = {}

    mine = next((r for r in rosters if r.roster_id == my_roster_id), None)
    my_ids = set(mine.players or []) if mine else set()

    my_links: list[HandcuffLink] = []
    for sid in my_ids:
        meta = players.get(sid, {})
        pos, team = meta.get("position"), meta.get("team")
        if pos not in SKILL_POSITIONS or not team:
            continue
        backup = backup_of(order, team, pos, sid)
        owner = _owner_label(backup)
        my_links.append(
            HandcuffLink(
                starter_id=sid,
                starter_name=meta.get("full_name") or sid,
                position=pos,
                team=team,
                backup_id=backup,
                backup_name=name_by_sid.get(backup) if backup else None,
                backup_owner=owner,
                status=classify_status(backup, owner),
            )
        )
    my_links.sort(key=lambda h: value_by_sid.get(h.starter_id, 0.0), reverse=True)
    exposed = [h for h in my_links if h.status == "EXPOSED"]

    # Leverage: an available backup directly behind a rival-owned starter.
    stashes: list[LeverageStash] = []
    for (team, pos), chain in order.items():
        if not chain:
            continue
        starter = chain[0]
        starter_owner_rid = owner_of.get(starter)
        if starter_owner_rid is None or starter_owner_rid == my_roster_id:
            continue
        backup = chain[1] if len(chain) > 1 else None
        if backup and backup not in owner_of:  # backup is a free agent
            stashes.append(
                LeverageStash(
                    backup_id=backup,
                    backup_name=name_by_sid.get(backup, backup),
                    position=pos,
                    team=team,
                    starter_name=name_by_sid.get(starter, starter),
                    starter_owner=f"roster:{starter_owner_rid}",
                )
            )
    stashes.sort(key=lambda s: value_by_sid.get(s.backup_id, 0.0), reverse=True)

    return HandcuffMap(
        season=DEFAULT_VALUE_SEASON,
        my_links=my_links,
        exposed=exposed,
        leverage_stashes=stashes[:12],
        warnings=warnings,
    )
