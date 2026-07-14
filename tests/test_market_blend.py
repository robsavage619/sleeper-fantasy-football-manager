from __future__ import annotations

from sleeper_ffm.market.blend import FC_TO_DYNASTY_SCALE as S
from sleeper_ffm.market.blend import blended_value, build_market_blend


def _wr_pool(fc_by_id: dict[str, float], model_by_id: dict[str, float]):
    positions = {pid: "WR" for pid in fc_by_id}
    return build_market_blend(model_by_id, positions, market=fc_by_id)


def test_empty_market_is_model_only() -> None:
    blend = build_market_blend({"a": 100.0}, {"a": "WR"}, market={})
    assert blend.model_valued_only
    value, market_valued = blended_value("a", "WR", 100.0, blend)
    assert value == 100.0
    assert market_valued is False


def test_blended_value_is_bounded_by_position_market_range() -> None:
    # The rank-based blend can never overshoot a position's market range — the
    # McBride-blended-above-both-inputs bug.
    fc = {"w1": 6000.0, "w2": 4000.0, "w3": 3000.0, "w4": 1500.0, "w5": 900.0}
    # A deliberately hot/uncorrelated model (w4 rated highest by the model).
    model = {"w1": 300.0, "w2": 90.0, "w3": 250.0, "w4": 800.0, "w5": 40.0}
    blend = _wr_pool(fc, model)
    lo, hi = min(fc.values()) * S, max(fc.values()) * S
    for pid in fc:
        value, market_valued = blended_value(pid, "WR", model[pid], blend)
        assert market_valued is True
        assert lo - 1e-6 <= value <= hi + 1e-6


def test_model_lifts_player_it_ranks_above_the_market() -> None:
    # w4 is bottom of the market but top by the model → blend should pull it above
    # its own market value (but stay within the position range).
    fc = {"w1": 6000.0, "w2": 4000.0, "w3": 3000.0, "w4": 1500.0}
    model = {"w1": 100.0, "w2": 80.0, "w3": 60.0, "w4": 900.0}
    blend = _wr_pool(fc, model)
    value, _ = blended_value("w4", "WR", model["w4"], blend)
    assert value > fc["w4"] * S
    assert value <= fc["w1"] * S + 1e-6


def test_market_only_position_uses_market_value() -> None:
    # QB is priced off the market alone (1QB replacement compression).
    model = {"q1": 0.0, "q2": 5.0, "q3": 250.0, "q4": 0.0}
    positions = {p: "QB" for p in model}
    fc = {"q1": 3700.0, "q2": 3200.0, "q3": 2000.0, "q4": 1300.0}
    blend = build_market_blend(model, positions, market=fc)
    for pid in fc:
        value, market_valued = blended_value(pid, "QB", model[pid], blend)
        assert market_valued is True
        assert abs(value - fc[pid] * S) < 1e-6  # exact market, not half, not aligned


def test_non_pool_player_is_model_only() -> None:
    fc = {"w1": 6000.0, "w2": 4000.0, "w3": 3000.0, "w4": 1500.0}
    model = {pid: v for pid, v in zip(fc, [400.0, 300.0, 200.0, 100.0], strict=True)}
    blend = _wr_pool(fc, model)
    value, market_valued = blended_value("not_in_pool", "WR", 55.0, blend)
    assert value == 55.0
    assert market_valued is False
