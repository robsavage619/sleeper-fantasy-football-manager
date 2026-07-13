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

The assistant never submits a pick. Pick submission is in ``act/playwright_driver.py``
(confirm-gated separately).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sleeper_ffm.config import DRAFT_ID, LEAGUE_ID, MY_ROSTER_ID, MY_USER_ID
from sleeper_ffm.model.dynasty import PickAsset, PlayerAsset, RosterAssets
from sleeper_ffm.prompts.draft import build_draft_prompt
from sleeper_ffm.sleeper.client import SleeperClient
from sleeper_ffm.sleeper.models import DraftPick

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
    my_slot: int  # pick slot in round (1-10)
    # slot_to_roster_id[slot] = roster_id (1-indexed str keys)
    slot_to_roster_id: dict[str, int] = field(default_factory=dict)

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
        """All overall pick numbers that belong to Rob (linear draft, fixed slot)."""
        return [self.my_slot + (r * self.total_teams) for r in range(self.total_rounds)]

    @property
    def next_my_pick(self) -> int | None:
        """The next pick number that is mine, or None if draft is over."""
        future = [n for n in self.my_pick_numbers if n >= self.current_pick_no]
        return future[0] if future else None

    @property
    def picks_until_my_turn(self) -> int:  # noqa: D102
        nxt = self.next_my_pick
        if nxt is None:
            return 0
        return nxt - self.current_pick_no

    def is_complete(self) -> bool:  # noqa: D102
        return len(self.picks_made) >= self.total_picks


def sync_board(
    draft_id: str = DRAFT_ID,
    my_roster_id: int = MY_ROSTER_ID,
) -> BoardState:
    """Fetch the current draft state from Sleeper.

    Args:
        draft_id: The Sleeper draft ID to query.
        my_roster_id: Rob's roster_id in this league.

    Returns:
        A ``BoardState`` snapshot of who has been picked and what's available.
    """
    with SleeperClient() as c:
        raw_draft = c._get(f"/draft/{draft_id}")
        picks_raw = c._get(f"/draft/{draft_id}/picks")

    settings = raw_draft.get("settings", {})
    total_rounds: int = settings.get("rounds", 4)
    total_teams: int = settings.get("teams", 10)
    slot_to_roster_id: dict[str, int] = {
        str(k): int(v) for k, v in (raw_draft.get("slot_to_roster_id") or {}).items()
    }

    # Determine my slot from slot_to_roster_id
    my_slot = 1
    for slot_str, rid in slot_to_roster_id.items():
        if rid == my_roster_id:
            my_slot = int(slot_str)
            break

    picks_made = [DraftPick.model_validate(p) for p in (picks_raw or [])]
    my_picks = [p for p in picks_made if p.roster_id == my_roster_id]
    taken = {p.player_id for p in picks_made if p.player_id}

    log.info(
        "board sync: %d/%d picks made, my slot=%d, my picks=%d",
        len(picks_made),
        total_rounds * total_teams,
        my_slot,
        len(my_picks),
    )

    return BoardState(
        draft_id=draft_id,
        total_rounds=total_rounds,
        total_teams=total_teams,
        picks_made=picks_made,
        my_picks=my_picks,
        taken_player_ids=taken,
        my_slot=my_slot,
        slot_to_roster_id=slot_to_roster_id,
    )


def build_my_roster(
    board: BoardState,
    player_assets: list[PlayerAsset],
    traded_picks: list[PickAsset] | None = None,
) -> RosterAssets:
    """Build a RosterAssets object for my team from picks made so far.

    Args:
        board: Current board state.
        player_assets: Full ranked asset list (to look up taken players by id).
        traded_picks: Future picks I hold (from league traded_picks endpoint).
    """
    asset_by_id = {p.player_id: p for p in player_assets}
    my_players: list[PlayerAsset] = []

    for pick in board.my_picks:
        if pick.player_id and pick.player_id in asset_by_id:
            my_players.append(asset_by_id[pick.player_id])
        elif pick.player_id:
            # Player in the draft but not in our nflverse asset list (likely rookie)
            my_players.append(
                PlayerAsset(
                    player_id=pick.player_id,
                    name=f"Player {pick.player_id}",
                    position="?",
                    age=22.0,
                    current_fpar=0.0,
                    is_taxi=True,  # treat unknown rookies as taxi-level
                )
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


def build_pick_prompt(
    board: BoardState,
    pool: list[PlayerAsset],
    traded_picks: list[PickAsset] | None = None,
    top_n: int = 25,
    vault_notes: str = "",
) -> str:
    """Build a structured prompt for Claude Code to reason over the next pick.

    Args:
        board: Current board state from ``sync_board()``.
        pool: Available player pool (unrostered + un-picked), sorted by dynasty value.
        traded_picks: Future picks held by my team.
        top_n: How many available players to show in the prompt.
        vault_notes: Optional vault research to inject.

    Returns:
        Prompt string ready to paste into Claude Code.
    """
    avail = pool[:top_n]
    my_roster = build_my_roster(board, pool, traded_picks)

    # Build all_picks map for positional run detection
    all_picks: dict[int, list[PickAsset]] = {}  # sparse — draft picks not yet valued
    # (traded_picks shows future ownership; in-draft picks are dynamic)

    picks_remaining = board.total_teams - board.pick_in_round

    return build_draft_prompt(
        pick_number=board.next_my_pick or board.current_pick_no,
        round_number=board.current_round,
        picks_remaining_in_round=picks_remaining,
        my_roster=my_roster,
        available_players=avail,
        all_picks=all_picks,
        scoring_summary=_scoring_summary(),
        top_n=top_n,
        vault_notes=vault_notes,
    )
