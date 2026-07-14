from __future__ import annotations

import pytest

from sleeper_ffm.model.dynasty import PickAsset, value_pick
from sleeper_ffm.prompts.trade import validate_trade_pick_ids, value_trade_pick


def test_trade_pick_id_formats_share_value_currency() -> None:
    # All three ID formats for the same pick resolve to one value, and that value
    # matches the dynasty currency's value_pick (no divergent pick math).
    expected = value_pick(PickAsset("2026", 2, 2, 2))
    assert value_trade_pick("2026_R2") == expected
    assert value_trade_pick("2026_2") == expected
    assert value_trade_pick("2026_2_6") == expected


def test_pick_values_are_ordered_by_round_and_market_scaled() -> None:
    # Earlier rounds are worth more, and picks are on the player value scale
    # (an early 1st is a real asset, ~150+, not a throwaway).
    r1 = value_trade_pick("2026_R1")
    r2 = value_trade_pick("2026_R2")
    r4 = value_trade_pick("2026_R4")
    assert r1 > r2 > r4 > 0
    assert r1 > 120


def test_invalid_trade_pick_ids_are_reported() -> None:
    assert validate_trade_pick_ids(["2026_R2", "bad", "2026_R5"]) == ["bad", "2026_R5"]


def test_value_trade_pick_raises_on_invalid_id() -> None:
    with pytest.raises(ValueError):
        value_trade_pick("bad")
