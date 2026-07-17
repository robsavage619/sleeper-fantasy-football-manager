"""Waiver wire analysis — trend-based priority scoring and FAAB estimation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sleeper_ffm.model.faab_market import FaabMarket, predicted_clearing_price
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

# Priority adjustment for how many of this roster's own players already sit at
# the candidate's position — trend score alone can't tell a real hole from an
# already-saturated position, and those are very different adds.
_POSITION_DEPTH_BONUS: dict[str, float] = {
    "HOLE": 12.0,
    "THIN": 6.0,
    "NORMAL": 0.0,
    "SURPLUS": -8.0,
}


def _positional_depth_tier(count: int) -> str:
    """Classify roster depth at a position from a rostered-player count."""
    if count == 0:
        return "HOLE"
    if count == 1:
        return "THIN"
    if count <= 3:
        return "NORMAL"
    return "SURPLUS"


def _my_position_counts(
    sleeper_players: dict[str, dict], my_roster_ids: set[str]
) -> dict[str, int]:
    """Count this roster's rostered players per skill position."""
    counts: dict[str, int] = dict.fromkeys(SKILL_POSITIONS, 0)
    for pid in my_roster_ids:
        pos = sleeper_players.get(pid, {}).get("position")
        if pos in counts:
            counts[pos] += 1
    return counts


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
    bid_min: int
    bid_max: int
    drop_candidate: str | None
    downside: str
    urgency: str
    decision: str
    rationale: str


def analyze_waivers(
    sleeper_players: dict[str, dict],
    trending_adds: list[TrendingPlayer],
    trending_drops: list[TrendingPlayer],
    rostered_ids: set[str],
    my_roster_ids: set[str] | None = None,
    protected_ids: set[str] | None = None,
    faab_budget: int = 500,
    faab_market: FaabMarket | None = None,
) -> list[WaiverCandidate]:
    """Score unrostered trending players for waiver priority.

    Priority formula (0-100 scale):
      - Trend score:   (adds / max_adds) * 50
      - Position bump: QB=15, TE=10, WR/RB=5 (1QB dynasty scarcity)
      - Net signal:    min(20, (adds - drops) / max_adds * 20) -- drops dilute
      - Youth bonus:   age < 24 -> +8, age 24-26 -> +4
      - Depth bonus:   +12 if this roster has 0 players at the position (a real
        hole), +6 if 1 (thin), 0 if 2-3 (normal), -8 if 4+ (already deep) --
        only applied when ``my_roster_ids`` is given; a raw trend score can't
        tell a genuine roster hole from chasing depth at an already-strong spot.
      Capped at 100.

    FAAB estimate: when ``faab_market`` has enough historical winning bids for the
    position, the priority tier is priced against this league's own bid percentiles
    (:func:`sleeper_ffm.model.faab_market.predicted_clearing_price`) instead of the
    generic 18%/10%/4%/$2 tiers, which have never seen an actual bid in this league.

    Args:
        sleeper_players: Full Sleeper player dump from SleeperClient.players().
        trending_adds: Trending add players from SleeperClient.trending("add").
        trending_drops: Trending drop players from SleeperClient.trending("drop").
        rostered_ids: Player IDs currently on any fantasy roster (excluded).
        my_roster_ids: Rob's rostered player IDs for drop-candidate selection.
        protected_ids: Starters or locked players that should not be suggested as drops.
        faab_budget: Total FAAB budget in dollars (default $500).
        faab_market: Optional built :class:`FaabMarket` for a league-grounded FAAB
            estimate; falls back to the generic tiers when omitted or thin on data.

    Returns:
        List of WaiverCandidate sorted by add_priority descending.
        Only unrostered SKILL_POSITIONS players are included.
    """
    add_map: dict[str, int] = {t.player_id: t.count for t in trending_adds}
    drop_map: dict[str, int] = {t.player_id: t.count for t in trending_drops}
    my_roster_ids = my_roster_ids or set()
    protected_ids = protected_ids or set()

    max_adds = max(add_map.values(), default=1)
    # Only computed (and only affects priority) when roster context is actually
    # given -- an empty my_roster_ids means "no signal," not "confirmed empty roster."
    my_position_counts = (
        _my_position_counts(sleeper_players, my_roster_ids) if my_roster_ids else None
    )

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
        depth_tier = _positional_depth_tier(my_position_counts[pos]) if my_position_counts else None
        depth_bonus = _POSITION_DEPTH_BONUS[depth_tier] if depth_tier else 0.0

        priority = round(
            min(100.0, trend_score + pos_bump + net_signal + youth_bonus + depth_bonus), 1
        )
        market_price = predicted_clearing_price(pos, priority, faab_market) if faab_market else None
        faab = (
            market_price + 1 if market_price is not None else _faab_estimate(priority, faab_budget)
        )
        faab = min(faab, faab_budget)
        bid_min, bid_max = _bid_range(faab, priority, faab_budget)
        drop_candidate = _drop_candidate(
            add_position=pos,
            sleeper_players=sleeper_players,
            my_roster_ids=my_roster_ids,
            protected_ids=protected_ids,
        )
        downside = _downside(adds=adds, drops=drops, age=age, pos=pos)
        urgency = "HIGH" if priority >= 75 else "MED" if priority >= 50 else "LOW"
        rationale = _build_rationale(adds, drops, age, pos, depth_tier)
        decision = (
            f"Claim if dropping {drop_candidate}; bid ${bid_min}-${bid_max}."
            if drop_candidate
            else f"Watch unless a roster spot opens; max bid ${bid_max}."
        )

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
                bid_min=bid_min,
                bid_max=bid_max,
                drop_candidate=drop_candidate,
                downside=downside,
                urgency=urgency,
                decision=decision,
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


def _bid_range(faab: int, priority: float, budget: int) -> tuple[int, int]:
    spread = 0.35 if priority >= 75 else 0.45 if priority >= 50 else 0.60
    low = max(1, round(faab * (1.0 - spread)))
    high = min(budget, max(faab, round(faab * (1.0 + spread))))
    return low, high


def _drop_candidate(
    add_position: str,
    sleeper_players: dict[str, dict],
    my_roster_ids: set[str],
    protected_ids: set[str],
) -> str | None:
    candidates: list[tuple[int, float, str]] = []
    for pid in my_roster_ids - protected_ids:
        player = sleeper_players.get(pid, {})
        pos = player.get("position", "")
        if pos not in SKILL_POSITIONS:
            continue
        rank = int(player.get("search_rank") or 9999)
        same_pos_bonus = 600 if pos == add_position else 0
        age = float(player.get("age") or 30)
        name = player.get("full_name") or f"Player {pid}"
        candidates.append((rank + same_pos_bonus, age, name))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def _downside(adds: int, drops: int, age: float, pos: str) -> str:
    if drops > adds * 0.5:
        return "Split market signal: drops are high relative to adds."
    if age >= 28 and pos != "QB":
        return "Short dynasty shelf life unless role spikes immediately."
    if adds < 500:
        return "Thin signal: trending volume is still modest."
    return "Mostly opportunity risk; confirm role before spending aggressively."


def _build_rationale(
    adds: int, drops: int, age: float, pos: str, depth_tier: str | None = None
) -> str:
    """Generate a human-readable waiver rationale string.

    Args:
        adds: Trending add count.
        drops: Trending drop count.
        age: Player age in years.
        pos: Position string (QB/RB/WR/TE).
        depth_tier: This roster's depth tier at ``pos`` ("HOLE"/"THIN"/"NORMAL"/
            "SURPLUS"), or None if roster context wasn't given. Only the two
            extremes are surfaced -- "normal" depth isn't worth a callout.

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
    if depth_tier == "HOLE":
        parts.append(f"fills a roster hole at {pos}")
    elif depth_tier == "SURPLUS":
        parts.append(f"already deep at {pos}")
    return " · ".join(parts)
