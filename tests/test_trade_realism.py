from __future__ import annotations

from sleeper_ffm.model.trade_acceptance import (
    TradeAsset,
    _acquire_premium,
    _impact,
    _leg_position,
)


def test_leg_position_classifies_names_picks_and_faab() -> None:
    name_to_pos = {"derrick henry": "RB", "joe burrow": "QB"}
    assert _leg_position("Derrick Henry", name_to_pos) == "RB"
    assert _leg_position("2026 R4", name_to_pos) == "PICK"
    assert _leg_position("$69 FAAB", name_to_pos) is None
    assert _leg_position("Unknown Guy", name_to_pos) is None


def test_acquire_premium_scales_with_demand() -> None:
    intel = {"liquidity": {"RB": 0.45, "WR": 0.32, "TE": 0.14, "QB": 0.08}}
    rb = _acquire_premium("RB", intel)
    wr = _acquire_premium("WR", intel)
    qb = _acquire_premium("QB", intel)
    # The most-traded position costs the biggest premium to pry loose.
    assert rb > wr > qb > 1.0


def test_impact_rewards_landing_a_need_and_penalizes_overpay() -> None:
    rb = TradeAsset(asset_id="1", kind="player", label="RB X", position="RB", value=180.0)
    fair, fair_label = _impact(rb, give_value=185.0, receive_value=180.0, my_needs={"RB"})
    gouged, _ = _impact(rb, give_value=260.0, receive_value=180.0, my_needs={"RB"})
    off_need, _ = _impact(rb, give_value=185.0, receive_value=180.0, my_needs={"WR"})
    assert fair_label == "HIGH"
    assert gouged < fair  # overpaying erodes impact
    assert off_need < fair  # a player who doesn't fill a need is worth far less


def test_impact_penalizes_trivial_swaps() -> None:
    flier = TradeAsset(asset_id="2", kind="player", label="Flier", position="RB", value=40.0)
    impact, label = _impact(flier, give_value=45.0, receive_value=40.0, my_needs={"RB"})
    assert label == "LOW"
    assert impact < 45


def test_impact_penalizes_timeline_mismatch() -> None:
    wr = TradeAsset(asset_id="3", kind="player", label="Vet WR", position="WR", value=180.0)
    fair, _ = _impact(wr, give_value=185.0, receive_value=180.0, my_needs={"WR"})
    mismatched, _ = _impact(
        wr, give_value=185.0, receive_value=180.0, my_needs={"WR"}, timeline_mismatch=True
    )
    assert mismatched < fair
    assert fair - mismatched == 25.0
