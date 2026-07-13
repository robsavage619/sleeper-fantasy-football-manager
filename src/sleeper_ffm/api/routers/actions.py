"""FastAPI router — prioritized War Room action queue."""

from __future__ import annotations

import dataclasses
import logging
import re
from dataclasses import dataclass

from fastapi import APIRouter, Query

log = logging.getLogger(__name__)

router = APIRouter(prefix="/war-room", tags=["war-room"])


@dataclass
class WarRoomAction:
    """One actionable recommendation for the GM queue."""

    action_id: str
    kind: str
    priority: int
    urgency: str
    title: str
    detail: str
    target: str | None
    confidence: str
    command: str
    source: str


_ACTION_RE = re.compile(r"Action:\s*(?P<action>.+)$")


def _system_action(action_id: str, title: str, detail: str) -> WarRoomAction:
    """Return a visible low-priority system notice."""
    return WarRoomAction(
        action_id=action_id,
        kind="SYSTEM",
        priority=10,
        urgency="LOW",
        title=title,
        detail=detail,
        target=None,
        confidence="HIGH",
        command="Inspect data source",
        source="system",
    )


def _trade_actions(limit: int) -> list[WarRoomAction]:
    """Build player-specific trade actions from the narrative intelligence."""
    from sleeper_ffm.prompts.narrative import build_narrative_context

    ctx = build_narrative_context()
    trade_lines: list[str] = ctx.sections.get("trade_angles", [])
    actions: list[WarRoomAction] = []
    for idx, line in enumerate(trade_lines[:limit], 1):
        clean = line.strip()
        target = clean.split(":", 1)[0] if ":" in clean else None
        match = _ACTION_RE.search(clean)
        command = match.group("action") if match else clean
        actions.append(
            WarRoomAction(
                action_id=f"trade-{idx}",
                kind="TRADE",
                priority=90 - idx,
                urgency="HIGH" if idx == 1 else "MED",
                title=f"Probe {target}" if target else "Send trade probe",
                detail=clean,
                target=target,
                confidence="MED",
                command=command,
                source="season/narrative",
            )
        )
    return actions


def _waiver_actions(limit: int) -> list[WarRoomAction]:
    """Build waiver actions from scored waiver candidates."""
    from sleeper_ffm.season.waivers import analyze_waivers
    from sleeper_ffm.sleeper.client import SleeperClient

    with SleeperClient() as client:
        trending_adds = client.trending("add", lookback_hours=24, limit=50)
        trending_drops = client.trending("drop", lookback_hours=24, limit=50)
        sleeper_players = client.players()
        rosters = client.rosters()

    rostered_ids: set[str] = set()
    for roster in rosters:
        rostered_ids.update(roster.players)

    candidates = analyze_waivers(
        sleeper_players=sleeper_players,
        trending_adds=trending_adds,
        trending_drops=trending_drops,
        rostered_ids=rostered_ids,
    )

    actions: list[WarRoomAction] = []
    for candidate in candidates[:limit]:
        actions.append(
            WarRoomAction(
                action_id=f"waiver-{candidate.player_id}",
                kind="WAIVER",
                priority=max(45, round(candidate.add_priority)),
                urgency="HIGH" if candidate.add_priority >= 75 else "MED",
                title=f"Watch {candidate.name}",
                detail=candidate.rationale,
                target=candidate.name,
                confidence="MED",
                command=f"Bid up to ${candidate.faab_estimate} FAAB if roster spot opens",
                source="season/waivers",
            )
        )
    return actions


def _pick_actions(limit: int) -> list[WarRoomAction]:
    """Build pick-market actions from model-vs-market signals."""
    from sleeper_ffm.model.pick_market import analyze_pick_market

    signals = [signal for signal in analyze_pick_market() if signal.signal != "HOLD"]
    actions: list[WarRoomAction] = []
    for idx, signal in enumerate(signals[:limit], 1):
        title = f"{signal.signal} {signal.season} R{signal.round}"
        actions.append(
            WarRoomAction(
                action_id=f"pick-{signal.season}-{signal.round}",
                kind="PICK",
                priority=65 - idx,
                urgency="MED",
                title=title,
                detail=signal.rationale,
                target=f"{signal.season} round {signal.round}",
                confidence="LOW" if signal.trade_count < 2 else "MED",
                command=(
                    "Shop for this pick below model value"
                    if signal.signal == "BUY"
                    else "Offer this pick for current player value"
                ),
                source="picks/market",
            )
        )
    return actions


def _lineup_actions() -> list[WarRoomAction]:
    """Build lineup actions when the NFL regular season is active."""
    from sleeper_ffm.season.startsit import build_startsit
    from sleeper_ffm.sleeper.client import SleeperClient

    with SleeperClient() as client:
        state = client.state_nfl()
    if state.season_type != "regular":
        return []

    season = int(state.season) if state.season and state.season.isdigit() else 2026
    rec = build_startsit(week=state.week or 1, season=season)
    actions: list[WarRoomAction] = []
    for idx, change in enumerate(rec.changes[:3], 1):
        player_pool = rec.projected_starters + rec.current_starters
        start_name = next(
            (p.name for p in player_pool if p.player_id == change["start"]),
            change["start"],
        )
        sit_name = next(
            (p.name for p in player_pool if p.player_id == change["sit"]),
            change["sit"],
        )
        actions.append(
            WarRoomAction(
                action_id=f"lineup-{idx}",
                kind="LINEUP",
                priority=85 - idx,
                urgency="HIGH",
                title=f"Start {start_name}",
                detail=f"Projected gain +{change['gain']:.1f} over {sit_name}",
                target=start_name,
                confidence="MED",
                command=f"Start {start_name}; sit {sit_name}",
                source="season/startsit",
            )
        )
    return actions


@router.get("/actions")
def war_room_actions(top: int = Query(default=12, ge=1, le=30)) -> list[dict]:
    """Return the prioritized GM action queue."""
    actions: list[WarRoomAction] = []
    builders = (
        ("trade intelligence", lambda: _trade_actions(limit=4)),
        ("waiver wire", lambda: _waiver_actions(limit=3)),
        ("pick market", lambda: _pick_actions(limit=3)),
        ("lineup optimizer", _lineup_actions),
    )

    for label, builder in builders:
        try:
            actions.extend(builder())
        except Exception as exc:
            log.exception("war-room action builder failed: %s", label)
            actions.append(
                _system_action(
                    action_id=f"system-{label.replace(' ', '-')}",
                    title=f"{label.title()} unavailable",
                    detail=str(exc),
                )
            )

    actions.sort(key=lambda action: (-action.priority, action.kind, action.title))
    return [dataclasses.asdict(action) for action in actions[:top]]
