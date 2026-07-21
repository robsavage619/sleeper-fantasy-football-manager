from __future__ import annotations

from sleeper_ffm.evals import waiver_arena as wa


def test_rank_and_score_perfect_ranking_hits_the_ceiling() -> None:
    candidates = ["a", "b", "c", "d"]
    projections = {"a": 30, "b": 20, "c": 10, "d": 5}  # ranks match reality
    realized = {"a": 30.0, "b": 20.0, "c": 10.0, "d": 5.0}
    out = wa.rank_and_score(candidates, projections, realized, top_k=2)
    assert out is not None
    engine, pool, optimal = out
    assert engine == optimal == 25.0  # top-2 by projection == top-2 by realized
    assert pool == 16.25  # mean of all four


def test_rank_and_score_random_ranking_matches_pool_in_expectation() -> None:
    candidates = ["a", "b", "c", "d"]
    projections = {"a": 1, "b": 1, "c": 1, "d": 1}  # no signal → ties, insertion order
    realized = {"a": 40.0, "b": 0.0, "c": 20.0, "d": 0.0}
    out = wa.rank_and_score(candidates, projections, realized, top_k=2)
    assert out is not None
    _engine, pool, optimal = out
    assert optimal == 30.0  # best two: 40 + 20
    assert pool == 15.0


def test_rank_and_score_wrong_ranking_underperforms_pool() -> None:
    candidates = ["a", "b", "c", "d"]
    projections = {"a": 1, "b": 2, "c": 30, "d": 40}  # projects the busts highest
    realized = {"a": 40.0, "b": 30.0, "c": 0.0, "d": 0.0}
    out = wa.rank_and_score(candidates, projections, realized, top_k=2)
    assert out is not None
    engine, pool, _ = out
    assert engine < pool  # backwards ranking does worse than random


def test_rank_and_score_needs_a_pool_bigger_than_k() -> None:
    assert wa.rank_and_score(["a", "b"], {"a": 1, "b": 1}, {"a": 1.0, "b": 1.0}, top_k=2) is None


def test_rank_and_score_ignores_candidates_with_no_realized_value() -> None:
    # 'x' has no realized entry (never resurfaced) → excluded from the pool.
    out = wa.rank_and_score(
        ["a", "b", "c", "x"], {"a": 3, "b": 2, "c": 1, "x": 99}, {"a": 3.0, "b": 2.0, "c": 1.0}, 1
    )
    assert out is not None
    engine, _pool, optimal = out
    assert engine == 3.0 and optimal == 3.0  # x is not scoreable, so 'a' leads


def test_completed_adds_collects_only_completed_transactions() -> None:
    txns = [
        {"status": "complete", "adds": {"111": 1, "222": 2}},
        {"status": "failed", "adds": {"333": 3}},
        {"status": "complete", "adds": None},
        {"status": "complete"},
    ]
    assert wa._completed_adds(txns) == {"111", "222"}
