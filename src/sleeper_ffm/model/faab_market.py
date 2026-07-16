"""FAAB clearing-price model — this league's actual historical willingness to pay.

Walks every waiver transaction across the full dynasty chain (same season-walk as
``owner_history.build_league_history``) and builds:

    * **League-wide winning-bid percentiles by position** — this league's real
      answer to "what does a WR2-priority add actually cost here", replacing the
      generic 18%/10%/4% tiers in ``season/waivers.py`` that have never seen this
      league's actual bids.
    * **Per-owner bid profiles** — where each manager's historical bids land
      relative to the league distribution, so "who's bidding against me" is a
      real read, not a guess.

Only WINNING bids are ever visible from Sleeper's public API — a losing bid amount
is never returned. Every number here is therefore a clearing-price floor, not a
full auction reconstruction: it can say "this is what it took to win", never "this
is what the runner-up offered".
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

import httpx

from sleeper_ffm.cache import ttl_cache
from sleeper_ffm.config import LEAGUE_ID
from sleeper_ffm.model.owner_history import _fetch_season_transactions
from sleeper_ffm.model.valuation import SKILL_POSITIONS
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

# Minimum winning bids observed for a position before its percentiles are trusted.
_MIN_BIDS_FOR_PERCENTILES = 5
# Minimum bids observed for an owner before an aggressiveness label is assigned.
_MIN_BIDS_FOR_OWNER_PROFILE = 3


@dataclass
class WaiverBid:
    """One winning waiver claim, as actually paid in this league."""

    season: str
    week: int
    roster_id: int  # current-season roster id (owner)
    player_id: str
    position: str
    bid: int


@dataclass
class PositionBidStats:
    """Winning-bid percentiles for one position, from this league's own history."""

    position: str
    n: int
    p25: float | None
    p50: float | None
    p75: float | None
    p90: float | None


@dataclass
class OwnerBidProfile:
    """One owner's historical FAAB spending pattern relative to the league."""

    roster_id: int
    n_bids: int
    median_bid: float | None
    aggressiveness: str  # "AGGRESSIVE" | "TYPICAL" | "CONSERVATIVE" | "UNKNOWN"


@dataclass
class FaabMarket:
    """Full FAAB clearing-price surface for the league."""

    seasons_covered: list[str]
    bids: list[WaiverBid]
    by_position: dict[str, PositionBidStats]
    by_owner: dict[int, OwnerBidProfile]
    warnings: list[str] = field(default_factory=list)


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile of a small sample (no extra dependency).

    Args:
        values: Sample (need not be sorted).
        pct: Target percentile in ``[0, 1]``.

    Returns:
        Interpolated value at ``pct``. Assumes ``values`` is non-empty.
    """
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _position_stats(position: str, bids: list[int]) -> PositionBidStats:
    if len(bids) < _MIN_BIDS_FOR_PERCENTILES:
        return PositionBidStats(
            position=position, n=len(bids), p25=None, p50=None, p75=None, p90=None
        )
    floats = [float(b) for b in bids]
    return PositionBidStats(
        position=position,
        n=len(bids),
        p25=round(_percentile(floats, 0.25), 1),
        p50=round(_percentile(floats, 0.50), 1),
        p75=round(_percentile(floats, 0.75), 1),
        p90=round(_percentile(floats, 0.90), 1),
    )


def _owner_profile(roster_id: int, bids: list[int], league_median: float) -> OwnerBidProfile:
    if len(bids) < _MIN_BIDS_FOR_OWNER_PROFILE:
        return OwnerBidProfile(
            roster_id=roster_id, n_bids=len(bids), median_bid=None, aggressiveness="UNKNOWN"
        )
    median_bid = statistics.median(bids)
    if league_median <= 0:
        aggressiveness = "UNKNOWN"
    elif median_bid >= league_median * 1.5:
        aggressiveness = "AGGRESSIVE"
    elif median_bid <= league_median * 0.6:
        aggressiveness = "CONSERVATIVE"
    else:
        aggressiveness = "TYPICAL"
    return OwnerBidProfile(
        roster_id=roster_id, n_bids=len(bids), median_bid=median_bid, aggressiveness=aggressiveness
    )


def build_bid_history(
    bids: list[WaiverBid],
) -> tuple[dict[str, PositionBidStats], dict[int, OwnerBidProfile]]:
    """Aggregate raw winning bids into position percentiles and owner profiles.

    Args:
        bids: Every winning waiver claim collected from the transaction walk.

    Returns:
        ``(by_position, by_owner)``.
    """
    by_position_raw: dict[str, list[int]] = {}
    by_owner_raw: dict[int, list[int]] = {}
    for b in bids:
        by_position_raw.setdefault(b.position, []).append(b.bid)
        by_owner_raw.setdefault(b.roster_id, []).append(b.bid)

    by_position = {pos: _position_stats(pos, vals) for pos, vals in by_position_raw.items()}

    all_bids = [b.bid for b in bids]
    league_median = statistics.median(all_bids) if all_bids else 0.0
    by_owner = {rid: _owner_profile(rid, vals, league_median) for rid, vals in by_owner_raw.items()}
    return by_position, by_owner


@ttl_cache()
def build_faab_market(league_id: str = LEAGUE_ID) -> FaabMarket:
    """Walk every season's waiver transactions and build the clearing-price surface.

    Args:
        league_id: Current-season Sleeper league ID.

    Returns:
        A :class:`FaabMarket`. Degrades to empty stats (with a warning) rather than
        raising when league history is unavailable.
    """
    warnings: list[str] = []
    with SleeperClient(league_id=league_id) as client:
        seasons = client.league_history(league_id=league_id)
        players_dump = client.players()

        if not seasons:
            return FaabMarket(
                seasons_covered=[],
                bids=[],
                by_position={},
                by_owner={},
                warnings=["No league history."],
            )

        current = seasons[0]
        current_rosters = client.rosters(league_id=current.league_id)
        user_to_current_roster = {r.owner_id or "": r.roster_id for r in current_rosters}

        seasons_covered: list[str] = []
        bids: list[WaiverBid] = []
        for league in seasons:
            season_str = league.season or league.league_id
            try:
                season_rosters = client.rosters(league_id=league.league_id)
            except httpx.HTTPError as exc:
                log.warning("faab_market: roster fetch failed for %s: %s", season_str, exc)
                continue
            seasons_covered.append(season_str)

            season_roster_to_current: dict[int, int] = {}
            for r in season_rosters:
                cur = user_to_current_roster.get(r.owner_id or "")
                if cur is not None:
                    season_roster_to_current[r.roster_id] = cur

            try:
                txns = _fetch_season_transactions(client, league.league_id)
            except httpx.HTTPError as exc:
                log.warning("faab_market: transaction walk failed for %s: %s", season_str, exc)
                continue

            for txn in txns:
                if txn.get("type") != "waiver":
                    continue
                bid_amount = int((txn.get("settings") or {}).get("waiver_bid", 0) or 0)
                if bid_amount <= 0:
                    continue
                week = int(txn.get("leg") or 0)
                for pid, season_roster in (txn.get("adds") or {}).items():
                    current_roster = season_roster_to_current.get(season_roster)
                    if current_roster is None:
                        continue
                    position = players_dump.get(pid, {}).get("position")
                    if position not in SKILL_POSITIONS:
                        continue
                    bids.append(
                        WaiverBid(
                            season=season_str,
                            week=week,
                            roster_id=current_roster,
                            player_id=pid,
                            position=position,
                            bid=bid_amount,
                        )
                    )

    if not bids:
        warnings.append("No winning waiver bids found in league history yet.")
    by_position, by_owner = build_bid_history(bids)
    return FaabMarket(
        seasons_covered=seasons_covered,
        bids=bids,
        by_position=by_position,
        by_owner=by_owner,
        warnings=warnings,
    )


def predicted_clearing_price(position: str, add_priority: float, market: FaabMarket) -> int | None:
    """Predict this league's likely winning bid for a player at a given priority tier.

    Maps the waiver-priority score (0-100, from ``season/waivers.py``) onto this
    league's own historical winning-bid percentile for the position: a top-tier
    add (priority >= 80) is priced at this league's 90th-percentile winning bid for
    that position, down through the 25th percentile for a thin add.

    Args:
        position: Player position (QB/RB/WR/TE).
        add_priority: 0-100 waiver priority score.
        market: A built :class:`FaabMarket`.

    Returns:
        Predicted clearing price in dollars, or ``None`` if this position doesn't
        have enough historical bids yet (falls back to the generic heuristic).
    """
    stats = market.by_position.get(position)
    if stats is None or stats.p50 is None:
        return None
    if add_priority >= 80:
        price = stats.p90
    elif add_priority >= 60:
        price = stats.p75
    elif add_priority >= 40:
        price = stats.p50
    else:
        price = stats.p25
    return round(price) if price is not None else None


def recommended_bid(
    position: str, add_priority: float, market: FaabMarket, budget_remaining: int
) -> int | None:
    """Second-price-plus-one recommendation from the predicted clearing price.

    Args:
        position: Player position.
        add_priority: 0-100 waiver priority score.
        market: A built :class:`FaabMarket`.
        budget_remaining: The bidder's remaining FAAB dollars.

    Returns:
        A bid capped at ``budget_remaining``, or ``None`` if no clearing price
        could be predicted (insufficient history for this position).
    """
    price = predicted_clearing_price(position, add_priority, market)
    if price is None:
        return None
    return max(1, min(budget_remaining, price + 1))
