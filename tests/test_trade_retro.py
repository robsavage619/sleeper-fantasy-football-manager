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


# --- roster-perspective audit --------------------------------------------------------


def _score(
    roster_a: int, roster_b: int, engine_pref: int, realized_winner: int, pa: float, pb: float
) -> tr.TradeScore:
    return tr.TradeScore(
        season=2023,
        week=5,
        roster_a=roster_a,
        roster_b=roster_b,
        engine_pref=engine_pref,
        realized_winner=realized_winner,
        correct=engine_pref == realized_winner,
        points_a=pa,
        points_b=pb,
    )


def test_roster_verdict_reframes_from_roster_a_perspective() -> None:
    # I'm roster 1 (roster_a); engine favored me, and I actually won on production.
    t = _score(roster_a=1, roster_b=2, engine_pref=1, realized_winner=1, pa=80.0, pb=30.0)
    v = tr._roster_verdict(t, target=1)
    assert v.partner_roster_id == 2
    assert v.engine_favored_me is True
    assert v.my_side_won is True
    assert v.points_delta == 50.0


def test_roster_verdict_reframes_from_roster_b_perspective() -> None:
    # I'm roster 2 (roster_b) in the same trade; engine favored the OTHER side, I lost.
    t = _score(roster_a=1, roster_b=2, engine_pref=1, realized_winner=1, pa=80.0, pb=30.0)
    v = tr._roster_verdict(t, target=2)
    assert v.partner_roster_id == 1
    assert v.engine_favored_me is False
    assert v.my_side_won is False
    assert v.points_delta == -50.0


def test_roster_verdict_engine_can_be_wrong_about_me() -> None:
    # Engine favored the other side, but I actually won on realized production anyway.
    t = _score(roster_a=1, roster_b=2, engine_pref=2, realized_winner=1, pa=60.0, pb=40.0)
    v = tr._roster_verdict(t, target=1)
    assert v.engine_favored_me is False
    assert v.my_side_won is True
    assert v.points_delta == 20.0


def test_audit_roster_trades_aggregates_engine_correct_and_net_points() -> None:
    trades = [
        _score(
            1, 2, engine_pref=1, realized_winner=1, pa=80.0, pb=30.0
        ),  # I'm 1: engine right, +50
        _score(
            1, 3, engine_pref=3, realized_winner=3, pa=20.0, pb=60.0
        ),  # I'm 1: engine right, -40
        _score(
            2, 1, engine_pref=2, realized_winner=1, pa=10.0, pb=90.0
        ),  # I'm roster_b=1: engine wrong about me, +80
    ]
    verdicts = [tr._roster_verdict(t, target=1) for t in trades]
    audit = tr.RosterTradeAudit(
        roster_id=1,
        seasons=(2023,),
        n_trades=len(verdicts),
        engine_correct=sum(1 for v in verdicts if v.engine_favored_me == v.my_side_won),
        net_points_delta=round(sum(v.points_delta for v in verdicts), 2),
        trades=verdicts,
    )
    # engine "correct" for me = its blind favorite matched who actually won: trades 1 and 2
    # match (favored me & I won; favored the other side & I lost); trade 3 does not
    # (favored roster 2, but I — roster 1 as roster_b — actually won).
    assert audit.engine_correct == 2
    assert audit.net_points_delta == 50.0 - 40.0 + 80.0
    s = audit.summary()
    assert "2/3" in s and "roster 1" in s


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
