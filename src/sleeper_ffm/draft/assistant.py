"""Draft assistant: live board sync + dynasty-valued pick recommendations.

The assistant coordinates three data sources:
  1. Sleeper draft API — which players have been taken (live board)
  2. ``model.valuation`` — FPAR-ranked available players
  3. ``prompts.draft`` — structured prompt for Claude Code

Usage pattern (called by the CLI ``sffm draft``):
    state = sync_board()                # live Sleeper fetch
    assets = build_player_assets()      # nflverse-scored dynasty values
    prompt = build_pick_prompt(state, assets)  # ready for Claude Code
    print(prompt)
    # Paste into Claude Code → Claude posts finding → dashboard renders

The assistant never submits a pick. The app is read-only until a confirm-gated action
layer is implemented.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sleeper_ffm.config import DRAFT_ID, LEAGUE_ID, MY_ROSTER_ID, MY_USER_ID
from sleeper_ffm.model.dynasty import PickAsset, PlayerAsset, RosterAssets
from sleeper_ffm.prompts.draft import build_draft_prompt
from sleeper_ffm.sleeper.client import SleeperClient
from sleeper_ffm.sleeper.models import DraftPick, TradedPick

log = logging.getLogger(__name__)


@dataclass
class BoardState:
    """Snapshot of a live draft board."""

    draft_id: str
    total_rounds: int
    total_teams: int
    picks_made: list[DraftPick]  # all picks so far (chronological)
    my_picks: list[DraftPick]  # only Rob's picks
    taken_player_ids: set[str]  # player_ids already off the board
    my_slot: int | None  # pick slot in round (1-10), or None if truly unknown
    # order_confirmed is False when Sleeper's own draft object has draft_order=null
    # (pre-draft placeholder state) — slot_to_roster_id is then an identity map, NOT
    # a real assignment. In that case my_slot may still be filled in from
    # order_projected (see below); it is never read off the meaningless placeholder.
    order_confirmed: bool = True
    # True when my_slot/slot_to_roster_id come from project_draft_order() (this
    # league's verified reverse-final-standings convention) rather than a
    # Sleeper-confirmed draft_order. Always False once order_confirmed is True.
    order_projected: bool = False
    projection_source_season: str | None = None
    # slot_to_roster_id[slot] = roster_id (1-indexed str keys)
    slot_to_roster_id: dict[str, int] = field(default_factory=dict)
    # Overall pick numbers I actually own, trade-adjusted across every round.
    # Empty when the slot order is unknown or the traded-pick fetch failed, in
    # which case my_pick_numbers falls back to the fixed-slot assumption.
    owned_pick_numbers: list[int] = field(default_factory=list)

    @property
    def total_picks(self) -> int:  # noqa: D102
        return self.total_rounds * self.total_teams

    @property
    def current_pick_no(self) -> int:
        """Next overall pick number (1-indexed)."""
        return len(self.picks_made) + 1

    @property
    def current_round(self) -> int:  # noqa: D102
        return (self.current_pick_no - 1) // self.total_teams + 1

    @property
    def pick_in_round(self) -> int:
        """Position within the current round (1-indexed)."""
        return (self.current_pick_no - 1) % self.total_teams + 1

    @property
    def my_pick_numbers(self) -> list[int]:
        """All overall pick numbers that belong to Rob (linear draft).

        Prefers owned_pick_numbers, which accounts for picks traded away or
        acquired in every round. The fixed-slot fallback below is only reached
        when trade data was unavailable (sync_board logs a warning); it is wrong
        for any round whose pick changed hands, so it is a last resort rather
        than the normal path.
        """
        if self.owned_pick_numbers:
            return self.owned_pick_numbers
        if self.my_slot is None:
            return []
        return [self.my_slot + (r * self.total_teams) for r in range(self.total_rounds)]

    @property
    def next_my_pick(self) -> int | None:
        """The next pick number that is mine, or None if unknown/draft is over."""
        future = [n for n in self.my_pick_numbers if n >= self.current_pick_no]
        return future[0] if future else None

    @property
    def picks_until_my_turn(self) -> int | None:
        """Picks remaining until my turn, or None if my_slot is unknown entirely."""
        if self.my_slot is None:
            return None
        nxt = self.next_my_pick
        if nxt is None:
            return 0
        return nxt - self.current_pick_no

    def is_complete(self) -> bool:  # noqa: D102
        return len(self.picks_made) >= self.total_picks


def resolve_owned_picks(
    slot_to_roster_id: dict[str, int],
    traded: list[TradedPick],
    draft_season: str,
    total_rounds: int,
    total_teams: int,
    my_roster_id: int,
) -> list[int]:
    """Overall pick numbers owned by ``my_roster_id``, adjusted for traded picks.

    In a linear draft the cell (round, slot) is overall pick
    ``(round - 1) * total_teams + slot``. A traded pick moves one such cell:
    ``TradedPick.roster_id`` is the cell's natural owner and ``owner_id`` holds
    it now. Both directions matter — a pick traded away has to disappear from
    the list and an acquired pick has to appear in it.

    Args:
        slot_to_roster_id: Draft slot (1-indexed str key) -> natural owner roster.
        traded: League traded picks (all seasons; filtered here).
        draft_season: Season of this draft, e.g. ``"2026"``.
        total_rounds: Rounds in the draft.
        total_teams: Teams in the draft.
        my_roster_id: The roster whose picks to resolve.

    Returns:
        Sorted overall pick numbers, empty when the slot map is empty.
    """
    owner_override = {
        (tp.round, tp.roster_id): tp.owner_id for tp in traded if tp.season == draft_season
    }
    owned: list[int] = []
    for rnd in range(1, total_rounds + 1):
        for slot_str, natural_rid in slot_to_roster_id.items():
            current_owner = owner_override.get((rnd, natural_rid), natural_rid)
            if current_owner == my_roster_id:
                owned.append((rnd - 1) * total_teams + int(slot_str))
    return sorted(owned)


def sync_board(
    draft_id: str = DRAFT_ID,
    my_roster_id: int = MY_ROSTER_ID,
    league_id: str = LEAGUE_ID,
) -> BoardState:
    """Fetch the current draft state from Sleeper.

    Args:
        draft_id: The Sleeper draft ID to query.
        my_roster_id: Rob's roster_id in this league.
        league_id: The league this draft belongs to (for the standings-based
            order projection fallback, and for resolving any traded picks).

    Returns:
        A ``BoardState`` snapshot of who has been picked and what's available.
    """
    with SleeperClient() as c:
        raw_draft = c._get(f"/draft/{draft_id}")
        picks_raw = c._get(f"/draft/{draft_id}/picks")

    settings = raw_draft.get("settings", {})
    total_rounds: int = settings.get("rounds", 4)
    total_teams: int = settings.get("teams", 10)
    draft_season = raw_draft.get("season") or ""
    slot_to_roster_id: dict[str, int] = {
        str(k): int(v) for k, v in (raw_draft.get("slot_to_roster_id") or {}).items()
    }

    # Sleeper sets draft_order to null until the commissioner (or auto-randomize)
    # assigns real slots. Until then, slot_to_roster_id is an identity placeholder
    # ({"1":1,"2":2,...}) — NOT a real assignment — so my_slot must never be read
    # off that map directly.
    order_confirmed = raw_draft.get("draft_order") is not None
    order_projected = False
    projection_source_season: str | None = None
    my_slot: int | None = None

    # Pick ownership is resolved per (round, slot) below, so trades matter in the
    # Sleeper-confirmed path just as much as in the projected one.
    try:
        with SleeperClient(league_id=league_id) as c2:
            traded = c2.traded_picks()
    except Exception as exc:
        log.warning(
            "traded_picks fetch failed; pick ownership falls back to the fixed-slot "
            "assumption and will be wrong for any traded round: %s",
            exc,
        )
        traded = []

    if order_confirmed:
        for slot_str, rid in slot_to_roster_id.items():
            if rid == my_roster_id:
                my_slot = int(slot_str)
                break
    else:
        # Fall back to this league's verified convention: reverse order of the
        # prior season's full final standings (see model.draft_order).
        try:
            from sleeper_ffm.model.draft_order import project_draft_order

            projection = project_draft_order(league_id)
        except Exception as exc:
            log.warning("draft order projection failed: %s", exc)
            projection = None

        if projection is not None:
            order_projected = True
            projection_source_season = projection.source_season
            slot_to_roster_id = {str(k): v for k, v in projection.slot_to_roster_id.items()}
            natural_owner_by_slot = dict(projection.slot_to_roster_id)

            # Round-1 trade awareness: my_slot is where I pick in round 1, so it
            # reflects an R1 pick traded away or acquired. Ownership in every
            # other round flows through owned_pick_numbers below.
            r1_owner_override: dict[int, int] = {}  # natural_owner_roster_id -> current owner
            for tp in traded:
                if tp.season == draft_season and tp.round == 1:
                    r1_owner_override[tp.roster_id] = tp.owner_id

            for slot_str, natural_rid in natural_owner_by_slot.items():
                current_owner = r1_owner_override.get(natural_rid, natural_rid)
                if current_owner == my_roster_id:
                    my_slot = slot_str
                    break

    picks_made = [DraftPick.model_validate(p) for p in (picks_raw or [])]
    my_picks = [p for p in picks_made if p.roster_id == my_roster_id]
    taken = {p.player_id for p in picks_made if p.player_id}

    # Only meaningful once the slot map is real: before that Sleeper serves an
    # identity placeholder, which would resolve to a bogus set of picks.
    owned_pick_numbers: list[int] = []
    if order_confirmed or order_projected:
        owned_pick_numbers = resolve_owned_picks(
            slot_to_roster_id=slot_to_roster_id,
            traded=traded,
            draft_season=draft_season,
            total_rounds=total_rounds,
            total_teams=total_teams,
            my_roster_id=my_roster_id,
        )

    log.info(
        "board sync: %d/%d picks made, order_confirmed=%s, order_projected=%s "
        "(from %s), my slot=%s, my picks=%d, owned pick numbers=%s",
        len(picks_made),
        total_rounds * total_teams,
        order_confirmed,
        order_projected,
        projection_source_season,
        my_slot,
        len(my_picks),
        owned_pick_numbers or "fixed-slot fallback",
    )

    return BoardState(
        draft_id=draft_id,
        total_rounds=total_rounds,
        total_teams=total_teams,
        picks_made=picks_made,
        my_picks=my_picks,
        taken_player_ids=taken,
        my_slot=my_slot,
        order_confirmed=order_confirmed,
        order_projected=order_projected,
        projection_source_season=projection_source_season,
        slot_to_roster_id=slot_to_roster_id,
        owned_pick_numbers=owned_pick_numbers,
    )


def build_my_roster(
    board: BoardState,
    player_assets: list[PlayerAsset],
    traded_picks: list[PickAsset] | None = None,
    sleeper_players: dict[str, dict] | None = None,
) -> RosterAssets:
    """Build a RosterAssets object for my team from picks made so far.

    Args:
        board: Current board state.
        player_assets: Full ranked asset list (to look up taken players by id).
        traded_picks: Future picks I hold (from league traded_picks endpoint).
        sleeper_players: Sleeper player dump, used to name and position rookies
            who have no nflverse history yet (fetched if None).
    """
    asset_by_id = {p.player_id: p for p in player_assets}
    my_players: list[PlayerAsset] = []
    unresolved: list[str] = []

    if sleeper_players is None:
        try:
            with SleeperClient() as client:
                sleeper_players = client.players()
        except Exception as exc:
            log.warning("build_my_roster: Sleeper dump unavailable: %s", exc)
            sleeper_players = {}

    for pick in board.my_picks:
        if pick.player_id and pick.player_id in asset_by_id:
            my_players.append(asset_by_id[pick.player_id])
        elif pick.player_id:
            # Just-drafted rookies have no nflverse history, so they carry no FPAR.
            # Identify them from the Sleeper dump anyway — an unnamed, position-less
            # entry is worse than useless in the middle of a draft.
            player = sleeper_players.get(pick.player_id, {})
            name = player.get("full_name") or player.get("search_full_name")
            position = player.get("position") or "?"
            age = player.get("age")
            if not name:
                unresolved.append(pick.player_id)
            my_players.append(
                PlayerAsset(
                    player_id=pick.player_id,
                    name=name or f"Player {pick.player_id}",
                    position=position,
                    age=float(age) if age else 22.0,
                    current_fpar=0.0,  # no NFL production to price yet
                    is_taxi=True,  # treat unknown rookies as taxi-level
                )
            )

    if unresolved:
        log.warning(
            "build_my_roster: %d drafted player(s) missing from both nflverse and "
            "the Sleeper dump, carrying zero value: %s",
            len(unresolved),
            unresolved,
        )

    return RosterAssets(
        roster_id=MY_ROSTER_ID,
        owner_id=MY_USER_ID,
        players=my_players,
        picks=traded_picks or [],
    )


def available_players(
    board: BoardState,
    player_assets: list[PlayerAsset],
) -> list[PlayerAsset]:
    """Filter player_assets to remove already-drafted players.

    Args:
        board: Current board state (taken_player_ids set).
        player_assets: Full ranked list sorted by dynasty value.

    Returns:
        Subset of player_assets not yet taken, same sort order.
    """
    return [p for p in player_assets if p.player_id not in board.taken_player_ids]


def build_full_pool(
    board: BoardState,
    seasons: list[int] | None = None,
    sleeper_players: dict | None = None,
    rookie_max_rank: int = 300,
) -> list[PlayerAsset]:
    """Build the full available draft pool (veterans + rookies, unrostered + un-picked).

    Combines nflverse FPAR for established players with Sleeper search_rank
    heuristics for rookies. The result is sorted by current_fpar.

    Args:
        board: Current board state (defines which players are already taken).
        seasons: nflverse seasons for veteran FPAR computation.
        sleeper_players: Pre-fetched Sleeper player dump (fetched if None).
        rookie_max_rank: Max Sleeper search_rank to include for rookies.
    """
    from sleeper_ffm.model.valuation import build_draft_pool
    from sleeper_ffm.sleeper.client import SleeperClient

    if sleeper_players is None:
        with SleeperClient() as c:
            sleeper_players = c.players()

    # Get all rostered IDs across the whole league (not just taken in this draft)
    with SleeperClient() as c:
        rosters = c.rosters()
    all_rostered: set[str] = set()
    for r in rosters:
        all_rostered.update(r.players or [])
        all_rostered.update(r.taxi or [])
        all_rostered.update(r.reserve or [])

    pool = build_draft_pool(
        rostered_ids=all_rostered,
        seasons=seasons,
        sleeper_players=sleeper_players,
        rookie_max_rank=rookie_max_rank,
    )

    # Also filter out picks made in THIS draft
    return [p for p in pool if p.player_id not in board.taken_player_ids]


def _scoring_summary(league_id: str = LEAGUE_ID) -> str:
    """Build a one-paragraph scoring rules description for the prompt."""
    with SleeperClient(league_id) as c:
        lg = c.league()
    s = lg.scoring_settings
    parts = [
        f"Full PPR (rec {s.get('rec', 1.0):.1f}pt)",
        f"pass_td {s.get('pass_td', 4):.0f}pt",
        f"rush/rec TD {s.get('rush_td', 6):.0f}pt",
        f"pass_yd {s.get('pass_yd', 0.04):.3f}pt",
        f"rush/rec_yd {s.get('rush_yd', 0.1):.2f}pt",
    ]
    bonuses = []
    bonus_map = {
        "bonus_rec_yd_100": "rec 100-yd",
        "bonus_rec_yd_200": "rec 200-yd",
        "bonus_rush_yd_100": "rush 100-yd",
        "bonus_rush_yd_200": "rush 200-yd",
        "bonus_pass_yd_300": "pass 300-yd",
        "bonus_pass_yd_400": "pass 400-yd",
        "bonus_pass_cmp_25": "25-cmp",
        "bonus_rush_att_20": "20-carry",
    }
    for key, label in bonus_map.items():
        val = s.get(key)
        if val:
            bonuses.append(f"{label}+{val:.1f}")
    if bonuses:
        parts.append(f"bonuses: {', '.join(bonuses)}")
    parts.append(f"INT {s.get('pass_int', -1):.0f}pt, fum_lost {s.get('fum_lost', -1):.0f}pt")
    return "; ".join(parts)


def build_all_picks_map(league_id: str = LEAGUE_ID) -> dict[int, list[PickAsset]]:
    """Fetch all traded future picks and return {current_owner_id: [PickAsset, ...]}.

    Used for positional run detection and pick-inventory context in draft prompts.
    Teams holding many future picks may reach; teams pick-poor need to draft for value.

    Args:
        league_id: Sleeper league ID.

    Returns:
        Dict mapping roster_id to the list of future picks that team currently holds.
        Falls back to empty dict on any network error.
    """
    try:
        with SleeperClient(league_id=league_id) as c:
            traded = c.traded_picks()
    except Exception as exc:
        log.warning("build_all_picks_map: fetch failed (%s); skipping pick inventory", exc)
        return {}

    picks_map: dict[int, list[PickAsset]] = {}
    for tp in traded:
        pick = PickAsset(
            season=tp.season,
            round=tp.round,
            original_owner_id=tp.roster_id,
            current_owner_id=tp.owner_id,
        )
        picks_map.setdefault(tp.owner_id, []).append(pick)
    return picks_map


def build_pick_prompt(
    board: BoardState,
    pool: list[PlayerAsset],
    traded_picks: list[PickAsset] | None = None,
    top_n: int = 25,
    vault_notes: str = "",
    market_values: dict[str, float] | None = None,
) -> str:
    """Build a structured prompt for Claude Code to reason over the next pick.

    Args:
        board: Current board state from ``sync_board()``.
        pool: Available player pool (unrostered + un-picked), sorted by dynasty value.
        traded_picks: Future picks held by my team.
        top_n: How many available players to show in the prompt.
        vault_notes: Optional vault research to inject.
        market_values: {sleeper_id: fc_value} for steal/reach signals (optional).

    Returns:
        Prompt string ready to paste into Claude Code.
    """
    avail = pool[:top_n]
    my_roster = build_my_roster(board, pool, traded_picks)
    all_picks = build_all_picks_map()
    picks_remaining = board.total_teams - board.pick_in_round

    return build_draft_prompt(
        pick_number=board.next_my_pick or board.current_pick_no,
        round_number=board.current_round,
        picks_remaining_in_round=picks_remaining,
        picks_until_my_turn=board.picks_until_my_turn,
        my_roster=my_roster,
        available_players=avail,
        all_picks=all_picks,
        scoring_summary=_scoring_summary(),
        top_n=top_n,
        vault_notes=vault_notes,
        market_values=market_values or {},
    )
