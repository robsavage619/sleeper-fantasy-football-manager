from __future__ import annotations

import pytest

from sleeper_ffm.prompts.trade import validate_trade_pick_ids, value_trade_pick


def test_trade_pick_id_formats_share_value_currency() -> None:
    assert value_trade_pick("2026_R2") == 50.0
    assert value_trade_pick("2026_2") == 50.0
    assert value_trade_pick("2026_2_6") == 50.0


def test_trade_pick_id_future_discount_matches_dynasty_currency() -> None:
    assert value_trade_pick("2027_R1") == 70.4


def test_invalid_trade_pick_ids_are_reported() -> None:
    assert validate_trade_pick_ids(["2026_R2", "bad", "2026_R5"]) == ["bad", "2026_R5"]


def test_value_trade_pick_raises_on_invalid_id() -> None:
    with pytest.raises(ValueError):
        value_trade_pick("bad")
