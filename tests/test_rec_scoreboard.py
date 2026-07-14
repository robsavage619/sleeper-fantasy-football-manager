"""Tests for the recommendation scoreboard (pure logic — no network)."""

from __future__ import annotations

from sleeper_ffm.model.rec_scoreboard import (
    TrackedRec,
    grade_lineup,
    grade_waiver,
    summarize,
)


def test_grade_lineup() -> None:
    assert grade_lineup(20.0, 12.0) == "CORRECT"
    assert grade_lineup(8.0, 15.0) == "INCORRECT"
    assert grade_lineup(10.0, 10.0) == "PUSH"
    assert grade_lineup(None, 10.0) == "PENDING"


def test_grade_waiver() -> None:
    assert grade_waiver([4.0, 14.0, 6.0]) == "HIT"
    assert grade_waiver([2.0, 5.0, 8.0]) == "MISS"
    assert grade_waiver([]) == "PENDING"
    assert grade_waiver(None) == "PENDING"


def _rec(kind: str, status: str) -> TrackedRec:
    return TrackedRec(finding_id="f", made_at="t", kind=kind, subject="s", status=status)


def test_summarize_hit_rate_excludes_pending_and_push() -> None:
    recs = [
        _rec("lineup", "CORRECT"),
        _rec("lineup", "INCORRECT"),
        _rec("lineup", "CORRECT"),
        _rec("lineup", "PUSH"),
        _rec("lineup", "PENDING"),
    ]
    by_kind, overall, graded, pending = summarize(recs)
    lineup = next(k for k in by_kind if k.kind == "lineup")
    assert lineup.graded == 3  # PUSH and PENDING excluded from graded
    assert lineup.correct == 2
    assert lineup.hit_rate == round(2 / 3, 3)
    assert overall == round(2 / 3, 3)
    assert graded == 3
    assert pending == 1


def test_summarize_none_hit_rate_when_all_pending() -> None:
    recs = [_rec("trade", "PENDING"), _rec("trade", "PENDING")]
    by_kind, overall, graded, pending = summarize(recs)
    assert by_kind[0].hit_rate is None
    assert overall is None
    assert graded == 0
    assert pending == 2
