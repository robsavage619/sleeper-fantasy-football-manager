"""Draft profile — how each manager drafts, and their best picks.

Walks every completed rookie/offseason draft in league history, attributes each
pick to the *current* manager (by Sleeper ``picked_by`` user id), and values the
drafted players by current FantasyCalc dynasty value. That surfaces real draft
skill: the hits, the steals, positional tendencies, and hit rate — none of which
needs weekly scoring, so this is a light, fast endpoint.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field

import httpx

from sleeper_ffm.config import LEAGUE_ID
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

_SKILL = ("QB", "RB", "WR", "TE")
# A drafted player is a "hit" once they're a real, rosterable dynasty asset.
_HIT_VALUE = 2000


@dataclass
class DraftedPlayer:
    """A player a manager drafted, valued by current dynasty market value."""

    player_id: str
    name: str
    position: str
    season: str
    round: int
    pick_no: int
    value: int
    rostered: bool


@dataclass
class DraftProfile:
    """A manager's draft tendencies, hit rate, and best picks across history."""

    roster_id: int
    display_name: str
    total_picks: int = 0
    seasons_drafted: int = 0
    position_mix: dict = field(default_factory=dict)
    position_lean: str = "—"
    hits: int = 0
    hit_rate: float = 0.0
    avg_pick_value: int = 0
    best_picks: list = field(default_factory=list)
    best_steal: dict | None = None


def build_draft_profiles(league_id: str = LEAGUE_ID) -> list[dict]:
    """Return per-manager draft tendencies + best picks across league history."""
    from sleeper_ffm.market.fantasycalc import fetch_full

    with SleeperClient(league_id=league_id) as client:
        seasons = client.league_history(league_id=league_id)
        if not seasons:
            return []
        current_rosters = client.rosters(league_id=seasons[0].league_id)
        user_to_current: dict[str, int] = {}
        rostered_by_current: dict[int, set[str]] = {}
        name_by_current: dict[int, str] = {}
        users = {
            u.user_id: (u.display_name or u.user_id) for u in client.users(seasons[0].league_id)
        }
        for r in current_rosters:
            uid = r.owner_id or ""
            user_to_current[uid] = r.roster_id
            rostered_by_current[r.roster_id] = set(r.players or [])
            name_by_current[r.roster_id] = users.get(uid, str(r.roster_id))

        picks_by_current: dict[int, list[DraftedPlayer]] = defaultdict(list)

        for league in seasons:
            try:
                drafts = client.league_drafts(league_id=league.league_id)
            except httpx.HTTPError:
                continue
            for d in drafts:
                if getattr(d, "status", None) != "complete":
                    continue
                try:
                    picks = client.draft_picks(d.draft_id)
                except httpx.HTTPError:
                    continue
                for p in picks:
                    cur = user_to_current.get(p.picked_by or "")
                    if cur is None:
                        continue
                    meta = p.metadata or {}
                    pid = p.player_id or meta.get("player_id") or ""
                    picks_by_current[cur].append(
                        DraftedPlayer(
                            player_id=pid,
                            name=(
                                f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
                                or f"Player {pid}"
                            ),
                            position=(meta.get("position") or "").upper(),
                            season=league.season or "",
                            round=p.round,
                            pick_no=p.pick_no,
                            value=0,  # filled from FantasyCalc below
                            rostered=False,
                        )
                    )

    try:
        fc = fetch_full()
    except Exception as exc:
        log.warning("draft_profile: FantasyCalc unavailable: %s", exc)
        fc = {}

    profiles: list[DraftProfile] = []
    for cur, picks in picks_by_current.items():
        for dp in picks:
            rec = fc.get(dp.player_id) or {}
            dp.value = int(rec.get("value") or 0)
            dp.rostered = dp.player_id in rostered_by_current.get(cur, set())

        skill_picks = [p for p in picks if p.position in _SKILL]
        mix: dict[str, int] = defaultdict(int)
        for p in skill_picks:
            mix[p.position] += 1

        hits = sum(1 for p in skill_picks if p.value >= _HIT_VALUE)
        seasons_drafted = len({p.season for p in picks})
        values = [p.value for p in skill_picks]
        avg_val = int(sum(values) / len(values)) if values else 0

        best_sorted = sorted(skill_picks, key=lambda p: p.value, reverse=True)
        best_picks = [asdict(p) for p in best_sorted[:5] if p.value > 0]
        steal_pool = [p for p in skill_picks if p.round >= 2 and p.value >= _HIT_VALUE]
        steal = max(steal_pool, key=lambda p: p.value) if steal_pool else None

        profiles.append(
            DraftProfile(
                roster_id=cur,
                display_name=name_by_current.get(cur, str(cur)),
                total_picks=len(picks),
                seasons_drafted=seasons_drafted,
                position_mix=dict(mix),
                position_lean=_lean(mix),
                hits=hits,
                hit_rate=round(hits / len(skill_picks), 2) if skill_picks else 0.0,
                avg_pick_value=avg_val,
                best_picks=best_picks,
                best_steal=asdict(steal) if steal else None,
            )
        )

    profiles.sort(key=lambda p: p.hit_rate, reverse=True)
    return [asdict(p) for p in profiles]


def _lean(mix: dict[str, int]) -> str:
    total = sum(mix.values())
    if not total:
        return "—"
    top_pos = max(mix, key=lambda k: mix[k])
    share = mix[top_pos] / total
    if share >= 0.45:
        return f"{top_pos}-HEAVY"
    if share >= 0.35:
        return f"{top_pos}-LEAN"
    return "BALANCED"
