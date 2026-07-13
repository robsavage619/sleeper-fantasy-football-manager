"""Waiver wire analysis — trend-based priority scoring and FAAB estimation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sleeper_ffm.model.valuation import SKILL_POSITIONS
from sleeper_ffm.sleeper.models import TrendingPlayer

log = logging.getLogger(__name__)

# 1QB dynasty position scarcity bump (points added to priority score).
_POSITION_BUMP: dict[str, float] = {
    "QB": 15.0,
    "TE": 10.0,
    "WR": 5.0,
    "RB": 5.0,
}


@dataclass
class WaiverCandidate:
    """A trending waiver-wire target with priority scoring and FAAB estimate."""

    player_id: str
    name: str
    position: str
    age: float
    team: str
    trending_adds: int
    trending_drops: int
    add_priority: float
    faab_estimate: int
    rationale: str


def analyze_waivers(
    sleeper_players: dict[str, dict],
    trending_adds: list[TrendingPlayer],
    trending_drops: list[TrendingPlayer],
    rostered_ids: set[str],
    faab_budget: int = 500,
) -> list[WaiverCandidate]:
    """Score unrostered trending players for waiver priority.

    Priority formula (0-100 scale):
      - Trend score:   (adds / max_adds) * 50
      - Position bump: QB=15, TE=10, WR/RB=5 (1QB dynasty scarcity)
      - Net signal:    min(20, (adds - drops) / max_adds * 20) -- drops dilute
      - Youth bonus:   age < 24 -> +8, age 24-26 -> +4
      Capped at 100.

    FAAB tiers: >=80 -> 18%, 60-80 -> 10%, 40-60 -> 4%, <40 -> $2 flat.

    Args:
        sleeper_players: Full Sleeper player dump from SleeperClient.players().
        trending_adds: Trending add players from SleeperClient.trending("add").
        trending_drops: Trending drop players from SleeperClient.trending("drop").
        rostered_ids: Player IDs currently on any fantasy roster (excluded).
        faab_budget: Total FAAB budget in dollars (default $500).

    Returns:
        List of WaiverCandidate sorted by add_priority descending.
        Only unrostered SKILL_POSITIONS players are included.
    """
    add_map: dict[str, int] = {t.player_id: t.count for t in trending_adds}
    drop_map: dict[str, int] = {t.player_id: t.count for t in trending_drops}

    max_adds = max(add_map.values(), default=1)

    candidates: list[WaiverCandidate] = []
    for pid, adds in add_map.items():
        if pid in rostered_ids:
            continue

        sp = sleeper_players.get(pid, {})
        pos = sp.get("position", "")
        if pos not in SKILL_POSITIONS:
            continue

        drops = drop_map.get(pid, 0)
        age = float(sp.get("age") or 25)
        name: str = sp.get("full_name") or f"Player {pid}"
        team: str = sp.get("team") or "FA"

        trend_score = (adds / max_adds) * 50.0
        pos_bump = _POSITION_BUMP.get(pos, 0.0)
        net_signal = min(20.0, (adds - drops) / max_adds * 20.0)
        youth_bonus = 8.0 if age < 24 else (4.0 if age <= 26 else 0.0)

        priority = round(min(100.0, trend_score + pos_bump + net_signal + youth_bonus), 1)
        faab = _faab_estimate(priority, faab_budget)
        rationale = _build_rationale(adds, drops, age, pos)

        candidates.append(
            WaiverCandidate(
                player_id=pid,
                name=name,
                position=pos,
                age=age,
                team=team,
                trending_adds=adds,
                trending_drops=drops,
                add_priority=priority,
                faab_estimate=faab,
                rationale=rationale,
            )
        )

    return sorted(candidates, key=lambda c: c.add_priority, reverse=True)


def _faab_estimate(priority: float, budget: int) -> int:
    """Convert a priority score to a FAAB dollar estimate.

    Args:
        priority: 0-100 priority score.
        budget: Total FAAB budget in dollars.

    Returns:
        Suggested FAAB bid in dollars.
    """
    if priority >= 80:
        return round(budget * 0.18)
    if priority >= 60:
        return round(budget * 0.10)
    if priority >= 40:
        return round(budget * 0.04)
    return 2


def _build_rationale(adds: int, drops: int, age: float, pos: str) -> str:
    """Generate a human-readable waiver rationale string.

    Args:
        adds: Trending add count.
        drops: Trending drop count.
        age: Player age in years.
        pos: Position string (QB/RB/WR/TE).

    Returns:
        Dot-separated rationale phrases.
    """
    parts: list[str] = [f"{adds} trending adds"]
    if drops > adds * 0.3:
        parts.append(f"{drops} drops offsetting")
    if age < 24:
        parts.append("youth upside")
    elif age <= 26:
        parts.append("prime years ahead")
    if pos == "QB":
        parts.append("QB scarcity")
    elif pos == "TE":
        parts.append("TE premium")
    return " · ".join(parts)
