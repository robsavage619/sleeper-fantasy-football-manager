"""League report-card grading — hermetic unit tests for the pure helpers."""

from __future__ import annotations

from sleeper_ffm.model import report_card as rc


def test_grade_for_rank_top_and_bottom() -> None:
    assert rc._grade_for_rank(1, 10) == "A+"
    assert rc._grade_for_rank(10, 10) == "D"


def test_grade_for_rank_monotonic() -> None:
    grades = [rc._grade_for_rank(r, 10) for r in range(1, 11)]
    # Distinct and ordered best → worst across a 10-team league.
    assert grades == ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D"]


def test_grade_for_rank_single_team() -> None:
    assert rc._grade_for_rank(1, 1) == "A+"


def test_rank_desc_orders_by_value() -> None:
    ranks = rc._rank_desc({1: 10.0, 2: 30.0, 3: 20.0})
    assert ranks == {2: 1, 3: 2, 1: 3}


def test_balance_score_penalizes_holes() -> None:
    deep = rc._balance_score({"QB": 2, "RB": 4, "WR": 5, "TE": 2})
    thin = rc._balance_score({"QB": 1, "RB": 1, "WR": 5, "TE": 0})
    assert deep > thin


def test_balance_score_empty_is_zero() -> None:
    assert rc._balance_score({}) == 0.0


def test_weights_sum_to_one() -> None:
    assert abs(sum(rc._WEIGHTS.values()) - 1.0) < 1e-9
