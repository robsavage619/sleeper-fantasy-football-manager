from __future__ import annotations

from sleeper_ffm.evals import trade_retro as tr


def test_score_trade_correct_when_engine_prefers_the_producer() -> None:
    received = {1: ["a"], 2: ["b"]}
    projected = {"a": 20.0, "b": 5.0}  # engine likes roster 1's side
    realized = {"a": 100.0, "b": 30.0}  # roster 1's side produced more
    out = tr.score_trade(received, projected, realized)
    assert out == (1, 1, True)


def test_score_trade_incorrect_when_engine_backs_the_wrong_side() -> None:
    received = {1: ["a"], 2: ["b"]}
    projected = {"a": 20.0, "b": 5.0}  # engine likes roster 1
    realized = {"a": 30.0, "b": 100.0}  # roster 2 actually produced more
    out = tr.score_trade(received, projected, realized)
    assert out == (1, 2, False)


def test_score_trade_multi_player_sides_sum() -> None:
    received = {1: ["a", "b"], 2: ["c"]}
    projected = {"a": 10.0, "b": 10.0, "c": 15.0}  # engine: side1 20 > side2 15
    realized = {"a": 40.0, "b": 40.0, "c": 50.0}  # side1 80 > side2 50
    assert tr.score_trade(received, projected, realized) == (1, 1, True)


def test_score_trade_none_on_realized_tie() -> None:
    received = {1: ["a"], 2: ["b"]}
    assert tr.score_trade(received, {"a": 9, "b": 1}, {"a": 50.0, "b": 50.0}) is None


def test_score_trade_none_when_a_side_received_no_scoreable_player() -> None:
    # roster 2's received player isn't in realized (e.g. a pick, filtered upstream).
    received = {1: ["a"], 2: ["pick"]}
    assert tr.score_trade(received, {"a": 9}, {"a": 50.0}) is None


def test_trade_retro_result_summary_pools_seasons() -> None:
    result = tr.TradeRetroResult(
        seasons=(2023, 2024),
        n_trades=10,
        engine_correct=7,
        correct_rate=0.7,
        sign_test_pvalue=0.34,
        trades=[],
    )
    s = result.summary()
    assert "2023/2024" in s and "7/10" in s and "70%" in s
