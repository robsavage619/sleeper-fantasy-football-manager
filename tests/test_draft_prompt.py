"""Draft prompt builder — deterministic unit tests (no network calls)."""

from __future__ import annotations

from sleeper_ffm.model.dynasty import PickAsset, PlayerAsset, RosterAssets
from sleeper_ffm.prompts.draft import (
    _survival_signal,
    _tier_label,
    build_draft_prompt,
)


def _player(pos: str, age: float, fpar: float, pid: str = "x") -> PlayerAsset:
    return PlayerAsset(player_id=pid, name=f"{pos}-{pid}", position=pos, age=age, current_fpar=fpar)


def _minimal_prompt(**overrides) -> str:
    defaults = dict(
        pick_number=5,
        round_number=1,
        picks_remaining_in_round=5,
        picks_until_my_turn=3,
        my_roster=RosterAssets(roster_id=1, owner_id="u1"),
        available_players=[_player("WR", 23, 80, "p1"), _player("RB", 22, 60, "p2")],
        all_picks={},
        scoring_summary="Full PPR",
        market_values={},
    )
    defaults.update(overrides)
    return build_draft_prompt(**defaults)


# ---- tier labels ----

def test_tier_label_t1() -> None:
    assert _tier_label(400.0) == "T1"


def test_tier_label_t3() -> None:
    assert _tier_label(150.0) == "T3"


def test_tier_label_t5() -> None:
    assert _tier_label(10.0) == "T5"


# ---- survival signal ----

def test_survival_gone_when_rank_lte_picks_until() -> None:
    assert _survival_signal(3, 3) == "GONE?"


def test_survival_risky_when_rank_lt_1_6x_picks_until() -> None:
    assert _survival_signal(4, 3) == "RISKY"


def test_survival_empty_when_safe() -> None:
    assert _survival_signal(10, 3) == ""


def test_survival_empty_on_clock() -> None:
    assert _survival_signal(1, 0) == ""


# ---- build_draft_prompt integration ----

def test_prompt_contains_pick_header() -> None:
    p = _minimal_prompt()
    assert "Pick 5 (Round 1)" in p


def test_prompt_contains_tier_label() -> None:
    p = _minimal_prompt()
    assert "[T" in p


def test_prompt_shows_all_picks_empty_message() -> None:
    p = _minimal_prompt(all_picks={})
    assert "no pick data" in p


def test_prompt_shows_all_picks_when_provided() -> None:
    all_picks = {
        2: [PickAsset(season="2027", round=1, original_owner_id=2, current_owner_id=2)]
    }
    p = _minimal_prompt(all_picks=all_picks)
    assert "Roster 2" in p
    assert "2027 R1" in p


def test_prompt_steal_flag_when_market_underprices() -> None:
    # Model DV for a 23yo WR with fpar=80 >> market_fpar = 4000/78 ≈ 51
    p = _minimal_prompt(
        available_players=[_player("WR", 23, 80, "p1")],
        market_values={"p1": 4000.0},
    )
    assert "★STEAL" in p


def test_prompt_reach_flag_when_model_overprices() -> None:
    # Model DV for a 23yo WR with fpar=80; market says 9500/78 ≈ 122 >> model
    p = _minimal_prompt(
        available_players=[_player("WR", 23, 80, "p1")],
        market_values={"p1": 9500.0},
    )
    assert "⚠REACH" in p


def test_prompt_no_signal_when_no_market_value() -> None:
    p = _minimal_prompt(
        available_players=[_player("WR", 23, 80, "p1")],
        market_values={},
    )
    # The legend always mentions STEAL/REACH; check that no player row has the star-signal.
    assert "★STEAL" not in p
    assert "⚠REACH" not in p


def test_prompt_empty_roster_message() -> None:
    p = _minimal_prompt(my_roster=RosterAssets(roster_id=1, owner_id="u1"))
    assert "empty" in p


def test_prompt_roster_shows_players() -> None:
    roster = RosterAssets(
        roster_id=1,
        owner_id="u1",
        players=[_player("WR", 24, 70, "p99")],
    )
    p = _minimal_prompt(my_roster=roster)
    assert "WR-p99" in p


def test_prompt_clock_label_on_clock() -> None:
    p = _minimal_prompt(picks_until_my_turn=0)
    assert "ON THE CLOCK" in p


def test_prompt_clock_label_waiting() -> None:
    p = _minimal_prompt(picks_until_my_turn=4)
    assert "4 picks away" in p
