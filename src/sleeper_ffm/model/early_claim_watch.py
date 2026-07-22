"""Early-claim watchlist — engine-flagged free agents the market hasn't priced yet.

The early-claim retro (``evals/early_claim.py``) measured a real, if modest, edge: the
engine's blind top-10 ranking flags roughly 2x as many season-defining pickups ahead of a
rival's claim as a random guess would. This is that ranking made live.

``best_available`` (``model/free_agents.py``) already ranks every unrostered player by
projection; ``wire_watch`` flags snap-share risers. What neither does is separate the
quiet value from the one everyone already sees: a top-projected free agent with a large
Sleeper trending-add count is already being bid on by the whole league regardless of what
this engine says, so recommending him is not an edge. The edge is the player who projects
well but hasn't shown up on the herd's radar yet — high engine value, low market attention.

Mechanism: take the free-agent board's wider pool, keep only players at or below
``_QUIET_TRENDING_MAX`` trending adds, and rank what's left by projection. Each claim gets
a drop suggestion (:func:`sleeper_ffm.season.waivers._drop_candidate`, the same worst-
droppable-skill-player heuristic the live waiver board already uses) and a reference FAAB
bid. Since a genuinely quiet player has no trending-add signal to price a bid tier from,
the reference bid uses this league's own median (50th-percentile) historical winning bid
for the position (:func:`~sleeper_ffm.model.faab_market.predicted_clearing_price`) rather
than inventing a new priority formula — an honest floor, not a claim of precision.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sleeper_ffm.config import MY_ROSTER_ID

if TYPE_CHECKING:
    from sleeper_ffm.model.faab_market import FaabMarket
    from sleeper_ffm.model.free_agents import FreeAgent

log = logging.getLogger(__name__)

_QUIET_TRENDING_MAX = 2
_DEFAULT_TOP_N = 8
_BOARD_POOL_SIZE = 40  # wider than the live best-available board so quiet gems survive
# No trend signal exists for a quiet player, so there is no priority tier to derive from
# adds/drops. This prices the reference bid at this league's own median winning bid for
# the position — a floor a manager should expect to clear, not a precision estimate.
_PRIORITY_PROXY = 50.0


@dataclass
class EarlyClaim:
    """One free agent the projection likes that the trending board hasn't caught up to."""

    player_id: str
    name: str
    position: str
    team: str
    projected_pts: float
    trending_add_count: int
    suggested_bid: int | None = None
    drop_candidate: str | None = None


@dataclass
class EarlyClaimWatch:
    """The live early-claim board for one week."""

    season: int
    week: int
    claims: list[EarlyClaim] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def rank_early_claims(
    pool: list[FreeAgent],
    my_roster_ids: set[str],
    sleeper_players: dict[str, dict],
    protected_ids: set[str] | None = None,
    faab_market: FaabMarket | None = None,
    top_n: int = _DEFAULT_TOP_N,
    quiet_trending_max: int = _QUIET_TRENDING_MAX,
) -> list[EarlyClaim]:
    """Rank a free-agent pool by projection, restricted to the market's blind spot.

    Pure given its inputs — ``pool`` is a list of
    :class:`~sleeper_ffm.model.free_agents.FreeAgent` (or anything with the same
    ``trending_add_count``/``projected_pts``/``position`` shape), ``faab_market`` an
    optional built :class:`~sleeper_ffm.model.faab_market.FaabMarket`.

    Args:
        pool: Candidate free agents, already excluding rostered players.
        my_roster_ids: This roster's player ids, for drop-candidate selection.
        sleeper_players: Full Sleeper player dump (drop-candidate lookups).
        protected_ids: Starters or locked players that should not be suggested as drops.
        faab_market: Built FAAB market for bid pricing; omit to skip bid estimates.
        top_n: How many quiet high-value claims to keep.
        quiet_trending_max: Trending-add count at or below which a player counts as
            "the market hasn't noticed."

    Returns:
        Up to ``top_n`` :class:`EarlyClaim` rows, highest-projected first.
    """
    from sleeper_ffm.model.faab_market import predicted_clearing_price
    from sleeper_ffm.season.waivers import _drop_candidate

    protected_ids = protected_ids or set()
    quiet = sorted(
        (fa for fa in pool if fa.trending_add_count <= quiet_trending_max),
        key=lambda fa: fa.projected_pts,
        reverse=True,
    )

    out: list[EarlyClaim] = []
    for fa in quiet[:top_n]:
        bid = (
            predicted_clearing_price(fa.position, _PRIORITY_PROXY, faab_market)
            if faab_market is not None
            else None
        )
        drop = _drop_candidate(fa.position, sleeper_players, my_roster_ids, protected_ids)
        out.append(
            EarlyClaim(
                player_id=fa.player_id,
                name=fa.name,
                position=fa.position,
                team=fa.team,
                projected_pts=fa.projected_pts,
                trending_add_count=fa.trending_add_count,
                suggested_bid=bid,
                drop_candidate=drop,
            )
        )
    return out


def build_early_claim_watch(
    my_roster_id: int = MY_ROSTER_ID, top_n: int = _DEFAULT_TOP_N
) -> EarlyClaimWatch:
    """Assemble the live early-claim watchlist.

    Args:
        my_roster_id: Roster to pick drop candidates from.
        top_n: Board size.

    Returns:
        An :class:`EarlyClaimWatch`. Degrades to an empty board with a warning if the
        free-agent board itself is unavailable; the FAAB market is best-effort and its
        absence only drops bid estimates, not the whole board.
    """
    from sleeper_ffm.model.free_agents import build_free_agent_board
    from sleeper_ffm.sleeper.client import SleeperClient

    board = build_free_agent_board(top_n=_BOARD_POOL_SIZE)
    if not board.overall:
        return EarlyClaimWatch(season=board.season, week=board.week, warnings=list(board.warnings))

    with SleeperClient() as client:
        sleeper_players = client.players()
        my_roster_ids: set[str] = set()
        protected_ids: set[str] = set()
        for roster in client.rosters():
            if int(roster.roster_id) == my_roster_id:
                my_roster_ids = set(roster.players or [])
                protected_ids = set(roster.starters or [])
                break

    market = None
    warnings = list(board.warnings)
    try:
        from sleeper_ffm.model.faab_market import build_faab_market

        market = build_faab_market()
    except Exception as exc:
        log.warning("early_claim_watch: faab market unavailable (%s)", exc)
        warnings.append("FAAB market unavailable — bids omitted.")

    claims = rank_early_claims(
        board.overall,
        my_roster_ids,
        sleeper_players,
        protected_ids=protected_ids,
        faab_market=market,
        top_n=top_n,
    )
    return EarlyClaimWatch(season=board.season, week=board.week, claims=claims, warnings=warnings)


__all__ = [
    "EarlyClaim",
    "EarlyClaimWatch",
    "build_early_claim_watch",
    "rank_early_claims",
]
