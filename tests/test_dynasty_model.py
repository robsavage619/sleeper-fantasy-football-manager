from __future__ import annotations

from sleeper_ffm.model.dynasty import (
    PickAsset,
    PlayerAsset,
    RosterAssets,
    asset_table,
    value_pick,
    value_player,
)
from sleeper_ffm.model.valuation import _is_draftable_veteran


def _player(pos: str, age: float, fpar: float, **kw) -> PlayerAsset:
    return PlayerAsset(player_id="x", name="Test", position=pos, age=age, current_fpar=fpar, **kw)


def test_young_wr_higher_than_old_wr() -> None:
    young = _player("WR", age=22, fpar=50)
    old = _player("WR", age=32, fpar=50)
    assert value_player(young) > value_player(old)


def test_zero_fpar_returns_zero() -> None:
    # current_fpar is already points above replacement.
    p = _player("RB", age=25, fpar=0.0)
    assert value_player(p) == 0.0


def test_below_replacement_clamps_zero() -> None:
    p = _player("RB", age=29, fpar=-3.0)
    assert value_player(p) == 0.0


def test_current_fpar_is_not_replacement_subtracted_twice() -> None:
    p = _player("RB", age=24, fpar=8.0)
    assert value_player(p) > 0.0


def test_taxi_penalty_applied() -> None:
    p_normal = _player("WR", age=22, fpar=30)
    p_taxi = _player("WR", age=22, fpar=30, is_taxi=True)
    # Taxi should be exactly 80% of normal
    assert abs(value_player(p_taxi) - value_player(p_normal) * 0.80) < 0.01


def test_rb_decays_faster_than_qb() -> None:
    # Equal FPAR and age-gap from peak: RB decays faster
    rb = _player("RB", age=28, fpar=40)  # 4 years past RB peak (24)
    qb = _player("QB", age=31, fpar=40)  # 4 years past QB peak (27)
    assert value_player(rb) < value_player(qb)


def test_pick_round1_more_than_round4() -> None:
    r1 = PickAsset(season="2026", round=1, original_owner_id=1, current_owner_id=1)
    r4 = PickAsset(season="2026", round=4, original_owner_id=1, current_owner_id=1)
    assert value_pick(r1) == 80.0
    assert value_pick(r4) == 10.0
    assert value_pick(r1) > value_pick(r4)


def test_pick_future_season_discounted() -> None:
    r1_now = PickAsset(season="2026", round=1, original_owner_id=1, current_owner_id=1)
    r1_future = PickAsset(season="2027", round=1, original_owner_id=1, current_owner_id=1)
    assert value_pick(r1_future) < value_pick(r1_now)


def test_old_free_agent_veteran_excluded_from_draft_pool() -> None:
    asset = PlayerAsset(
        player_id="vet",
        name="Old Free Agent",
        position="TE",
        age=30,
        current_fpar=80,
        team="FA",
    )
    sleeper_players = {"vet": {"years_exp": 8, "search_rank": 999, "team": None}}
    assert not _is_draftable_veteran(asset, sleeper_players)


def test_pick_class_strength_multiplier() -> None:
    base = {"season": "2026", "round": 1, "original_owner_id": 1, "current_owner_id": 1}
    weak = PickAsset(**base, class_strength=0.8)
    strong = PickAsset(**base, class_strength=1.2)
    assert value_pick(strong) > value_pick(weak)


def test_roster_total_value() -> None:
    roster = RosterAssets(
        roster_id=1,
        owner_id="u1",
        players=[_player("WR", age=24, fpar=40), _player("RB", age=23, fpar=30)],
        picks=[PickAsset(season="2026", round=1, original_owner_id=1, current_owner_id=1)],
    )
    assert roster.total_value == roster.player_value + roster.pick_value
    assert roster.total_value > 0


def test_asset_table_sorted_descending() -> None:
    roster = RosterAssets(
        roster_id=1,
        owner_id="u1",
        players=[_player("RB", age=30, fpar=10), _player("WR", age=22, fpar=60)],
        picks=[PickAsset(season="2027", round=4, original_owner_id=1, current_owner_id=1)],
    )
    table = asset_table(roster)
    values = [row["value"] for row in table]
    assert values == sorted(values, reverse=True)
