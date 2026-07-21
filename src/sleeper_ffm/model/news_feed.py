"""Real-world intelligence feed that grounds the engines in current status.

Aggregates the signals the valuation/trade/waiver/start-sit surfaces were flying
blind to: injuries, depth-chart standing, recent news, opportunity created when a
starter goes down, and what rivals are doing in-league. Everything is sourced
from data already on hand — the Sleeper player dump (``injury_status``,
``depth_chart_order``, ``news_updated``) and Sleeper league transactions — so the
feed needs no new provider. Volume is naturally thin in the off-season and lights
up in-season.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.config import MY_ROSTER_ID
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

_SKILL: frozenset[str] = frozenset({"QB", "RB", "WR", "TE"})
# injury_status values that materially threaten availability.
_OUT_STATUSES: frozenset[str] = frozenset({"Out", "IR", "PUP", "Sus", "DNR", "NA"})
_QUESTION_STATUSES: frozenset[str] = frozenset({"Questionable", "Doubtful"})


@dataclass
class PlayerAlert:
    """One real-world status signal about a player."""

    player_id: str
    name: str
    position: str
    team: str
    kind: str  # INJURY | DEPTH | OPPORTUNITY
    severity: str  # WARN | WATCH | INFO
    detail: str


@dataclass
class IntelFeed:
    """Aggregated real-world intelligence for one roster's decision surfaces."""

    roster_alerts: list[PlayerAlert] = field(default_factory=list)
    opportunities: list[PlayerAlert] = field(default_factory=list)
    league_moves: list[dict] = field(default_factory=list)
    generated_note: str = ""


@ttl_cache(ttl=900)
def _players() -> dict[str, dict]:
    with SleeperClient() as c:
        return c.players()


# Questionable players suit up ~75-80% of the time; a Doubtful designation is nearly an
# Out. The 0.8 shade for Questionable is the value the arena validated out-of-sample
# (evals/arena.py: injury gating lifted lineup capture ~4 points).
_QUESTIONABLE_PLAY_FACTOR = 0.8


def availability_factor(injury_status: str | None) -> float:
    """Multiplier for a player's projection given his Sleeper injury designation.

    The canonical availability shade, owned here beside the status vocabulary it uses so
    every surface (start/sit, intel, briefings) discounts identically. Out-class statuses
    and Doubtful zero the projection; Questionable shades it; everything else is unchanged.

    Args:
        injury_status: The Sleeper ``injury_status`` value, or None for healthy/unknown.

    Returns:
        A multiplier in ``[0.0, 1.0]``.
    """
    if not injury_status:
        return 1.0
    if injury_status in _OUT_STATUSES or injury_status == "Doubtful":
        return 0.0
    if injury_status == "Questionable":
        return _QUESTIONABLE_PLAY_FACTOR
    return 1.0


def _injury_alert(player: dict) -> PlayerAlert | None:
    """Build an injury alert from a Sleeper player record, if noteworthy."""
    status = player.get("injury_status")
    if not status:
        return None
    if status in _OUT_STATUSES:
        severity = "WARN"
    elif status in _QUESTION_STATUSES:
        severity = "WATCH"
    else:
        return None
    note = player.get("injury_notes") or player.get("injury_body_part") or ""
    practice = player.get("practice_participation")
    detail = status + (f" — {note}" if note else "")
    if practice:
        detail += f" (practice: {practice})"
    return PlayerAlert(
        player_id=player.get("player_id", ""),
        name=player.get("full_name") or player.get("player_id", ""),
        position=player.get("position", ""),
        team=player.get("team") or "FA",
        kind="INJURY",
        severity=severity,
        detail=detail,
    )


def _depth_alert(player: dict) -> PlayerAlert | None:
    """Flag a rostered player who is buried on the depth chart (role risk)."""
    order = player.get("depth_chart_order")
    if not isinstance(order, int) or order < 3:
        return None
    return PlayerAlert(
        player_id=player.get("player_id", ""),
        name=player.get("full_name") or player.get("player_id", ""),
        position=player.get("position", ""),
        team=player.get("team") or "FA",
        kind="DEPTH",
        severity="WATCH",
        detail=f"buried at depth-chart #{order} ({player.get('depth_chart_position') or '?'})",
    )


def roster_alerts(roster_id: int = MY_ROSTER_ID) -> list[PlayerAlert]:
    """Injury + depth-chart alerts for the players on one roster."""
    players = _players()
    with SleeperClient() as c:
        rosters = c.rosters()
    roster = next((r for r in rosters if r.roster_id == roster_id), None)
    if roster is None:
        return []

    alerts: list[PlayerAlert] = []
    for pid in roster.players:
        player = players.get(pid)
        if not player or player.get("position") not in _SKILL:
            continue
        injury = _injury_alert(player)
        if injury:
            alerts.append(injury)
        depth = _depth_alert(player)
        if depth:
            alerts.append(depth)
    severity_rank = {"WARN": 0, "WATCH": 1, "INFO": 2}
    alerts.sort(key=lambda a: (severity_rank.get(a.severity, 3), a.name))
    return alerts


def opportunity_board(limit: int = 15) -> list[PlayerAlert]:
    """Unrostered-in-spirit players who inherit a role when the starter is down.

    For each team+position, if the depth-chart starter is injured/out, the next
    man up is a live opportunity — the signal waivers should chase before the herd.
    """
    players = _players()
    # Index the injured starters by (team, depth_chart_position).
    injured_ahead: set[tuple[str, str]] = set()
    for p in players.values():
        if (
            p.get("position") in _SKILL
            and p.get("injury_status") in _OUT_STATUSES
            and isinstance(p.get("depth_chart_order"), int)
            and p["depth_chart_order"] == 1
            and p.get("team")
            and p.get("depth_chart_position")
        ):
            injured_ahead.add((p["team"], p["depth_chart_position"]))

    out: list[PlayerAlert] = []
    for p in players.values():
        if p.get("position") not in _SKILL or not p.get("active"):
            continue
        team = p.get("team")
        slot = p.get("depth_chart_position")
        order = p.get("depth_chart_order")
        if (
            team
            and slot
            and isinstance(order, int)
            and order == 2
            and (team, slot) in injured_ahead
            and p.get("injury_status") not in _OUT_STATUSES
        ):
            out.append(
                PlayerAlert(
                    player_id=p.get("player_id", ""),
                    name=p.get("full_name") or p.get("player_id", ""),
                    position=p.get("position", ""),
                    team=team,
                    kind="OPPORTUNITY",
                    severity="INFO",
                    detail=f"next up at {slot} — starter is out; snap/role bump likely",
                )
            )
    return out[:limit]


def league_moves(weeks: int = 3, roster_id: int = MY_ROSTER_ID) -> list[dict]:
    """Recent completed transactions by rivals (trades, waivers, free-agent adds)."""
    players = _players()

    def _names(ids: dict | None) -> list[str]:
        if not ids:
            return []
        return [(players.get(pid) or {}).get("full_name") or pid for pid in ids]

    moves: list[dict] = []
    with SleeperClient() as c:
        state = c.state_nfl()
        current_week = max(1, int(getattr(state, "week", 1) or 1))
        for week in range(max(1, current_week - weeks + 1), current_week + 1):
            try:
                txns = c.transactions(week)
            except Exception as exc:
                log.warning("league_moves: week %d transactions failed: %s", week, exc)
                continue
            for t in txns:
                if t.get("status") != "complete":
                    continue
                moves.append(
                    {
                        "week": week,
                        "type": t.get("type"),
                        "roster_ids": t.get("roster_ids", []),
                        "adds": _names(t.get("adds")),
                        "drops": _names(t.get("drops")),
                        "involves_me": roster_id in (t.get("roster_ids") or []),
                    }
                )
    return moves


def build_feed(roster_id: int = MY_ROSTER_ID) -> IntelFeed:
    """Assemble the full real-world intelligence feed for one roster."""
    alerts = roster_alerts(roster_id)
    opps = opportunity_board()
    moves = league_moves(roster_id=roster_id)
    note = (
        f"{len(alerts)} roster alert(s), {len(opps)} opportunity signal(s), "
        f"{len(moves)} recent league move(s). Injury/news volume is low in the "
        "off-season and rises in-season."
    )
    return IntelFeed(
        roster_alerts=alerts,
        opportunities=opps,
        league_moves=moves,
        generated_note=note,
    )
