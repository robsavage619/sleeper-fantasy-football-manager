"""Traded-pick-aware draft pick ownership — deterministic unit tests (no network)."""

from __future__ import annotations

from sleeper_ffm.draft.assistant import BoardState, resolve_owned_picks
from sleeper_ffm.sleeper.models import TradedPick

# 10-team linear draft, slot == roster_id for readability.
SLOTS = {str(i): i for i in range(1, 11)}
ROUNDS = 4
TEAMS = 10


def _traded(rnd: int, natural: int, owner: int, season: str = "2026") -> TradedPick:
    return TradedPick(season=season, round=rnd, roster_id=natural, owner_id=owner)


def _owned(traded: list[TradedPick], my_roster_id: int = 2) -> list[int]:
    return resolve_owned_picks(
        slot_to_roster_id=SLOTS,
        traded=traded,
        draft_season="2026",
        total_rounds=ROUNDS,
        total_teams=TEAMS,
        my_roster_id=my_roster_id,
    )


def test_no_trades_gives_one_pick_per_round() -> None:
    assert _owned([]) == [2, 12, 22, 32]


def test_pick_traded_away_disappears() -> None:
    # Rob's (roster 2) natural round-2 pick now belongs to roster 3 — the real
    # 2026 trade that motivated this fix.
    assert _owned([_traded(2, natural=2, owner=3)]) == [2, 22, 32]


def test_acquired_pick_appears() -> None:
    # Roster 7's round-1 pick acquired: slot 7 in round 1 is overall pick 7.
    assert _owned([_traded(1, natural=7, owner=2)]) == [2, 7, 12, 22, 32]


def test_traded_away_and_acquired_together() -> None:
    # Lose my round 2 (pick 12), gain roster 9's round 3 (pick 29).
    traded = [_traded(2, natural=2, owner=3), _traded(3, natural=9, owner=2)]
    assert _owned(traded) == [2, 22, 29, 32]


def test_pick_returned_to_natural_owner_is_kept() -> None:
    # Sleeper records a round trip as owner_id == roster_id.
    assert _owned([_traded(3, natural=2, owner=2)]) == [2, 12, 22, 32]


def test_other_season_trades_are_ignored() -> None:
    assert _owned([_traded(2, natural=2, owner=3, season="2027")]) == [2, 12, 22, 32]


def test_empty_slot_map_yields_nothing() -> None:
    assert (
        resolve_owned_picks(
            slot_to_roster_id={},
            traded=[],
            draft_season="2026",
            total_rounds=ROUNDS,
            total_teams=TEAMS,
            my_roster_id=2,
        )
        == []
    )


# ---- BoardState wiring ----


def _board(**overrides) -> BoardState:
    defaults = dict(
        draft_id="d1",
        total_rounds=ROUNDS,
        total_teams=TEAMS,
        picks_made=[],
        my_picks=[],
        taken_player_ids=set(),
        my_slot=2,
        slot_to_roster_id=SLOTS,
    )
    defaults.update(overrides)
    return BoardState(**defaults)


def test_board_prefers_owned_pick_numbers() -> None:
    board = _board(owned_pick_numbers=[2, 22, 32])
    assert board.my_pick_numbers == [2, 22, 32]


def test_board_falls_back_to_fixed_slot_without_trade_data() -> None:
    assert _board().my_pick_numbers == [2, 12, 22, 32]


def test_countdown_skips_the_traded_round() -> None:
    # 12 picks in: the fixed-slot assumption would claim pick 12 (round 2) was
    # mine and count down to a turn that belongs to roster 3.
    board = _board(owned_pick_numbers=[2, 22, 32], picks_made=[None] * 12)
    assert board.next_my_pick == 22
    assert board.picks_until_my_turn == 9


def test_no_slot_and_no_trade_data_is_unknown() -> None:
    board = _board(my_slot=None)
    assert board.my_pick_numbers == []
    assert board.picks_until_my_turn is None
