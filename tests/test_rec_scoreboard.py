"""Tests for the recommendation scoreboard (pure logic — no network)."""

from __future__ import annotations

import datetime as dt

import polars as pl

from sleeper_ffm.model import rec_scoreboard as rs
from sleeper_ffm.model.rec_scoreboard import (
    TrackedRec,
    grade_lineup,
    grade_waiver,
    summarize,
)
from sleeper_ffm.reasoning.findings import Finding


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


# ── extraction fan-out fix + outcome grading ─────────────────────────────────


def _finding(kind: str, body: dict, created_at: float) -> Finding:
    return Finding(finding_id=f"{kind}_x", kind=kind, body=body, created_at=created_at)


def test_normalize_name_strips_annotation_and_suffix() -> None:
    assert rs.normalize_name("Bijan Robinson (RB ATL)") == "bijan robinson"
    assert rs.normalize_name("Marvin Harrison Jr.") == "marvin harrison"
    assert rs.normalize_name("Amon-Ra St. Brown") == rs.normalize_name("Amon-Ra St Brown")


def test_extract_recs_reads_fanned_out_findings() -> None:
    """The core bug: bulk-posted findings are one-rec-per-finding, keyed by finding.kind."""
    findings = [
        _finding(
            "lineup",
            {"start": "Bijan Robinson", "sit": "Zack Moss", "rationale": "matchup"},
            1_700_000_000,
        ),
        _finding("waiver", {"player": "Jauan Jennings", "faab_bid": 14}, 1_700_000_000),
        _finding("trade", {"partner": "Rival A", "receive": "WR1"}, 1_700_000_000),
    ]
    recs = rs._extract_recs(findings)
    assert sorted(r.kind for r in recs) == ["lineup", "trade", "waiver"]
    lineup = next(r for r in recs if r.kind == "lineup")
    assert lineup.start == "Bijan Robinson" and lineup.sit == "Zack Moss"
    assert all(r.status == "PENDING" for r in recs)


def test_extract_recs_handles_legacy_nested_document() -> None:
    body = {
        "trade_recs": [{"partner": "A", "receive": "WR1"}],
        "lineup_recs": [{"start": "P1", "sit": "P2"}],
    }
    recs = rs._extract_recs([_finding("narrative", body, 1_700_000_000)])
    assert sorted(r.kind for r in recs) == ["lineup", "trade"]


def test_grade_tracked_recs_scores_lineup_and_waiver() -> None:
    recs = [
        TrackedRec(
            "f1", "", "lineup", "", "PENDING", start="Player A", sit="Player B", made_at_epoch=1.0
        ),
        TrackedRec(
            "f2", "", "lineup", "", "PENDING", start="Player A", sit="Player C", made_at_epoch=1.0
        ),
        TrackedRec("f3", "", "waiver", "", "PENDING", player="Player D", made_at_epoch=1.0),
        TrackedRec("f4", "", "waiver", "", "PENDING", player="Player E", made_at_epoch=1.0),
    ]
    weekly_fp = {
        "player a": {(2025, 5): 18.0},
        "player b": {(2025, 5): 10.0},
        "player c": {(2025, 5): 25.0},
        "player d": {(2025, 5): 6.0, (2025, 6): 15.0},  # cleared startable in wk6
        "player e": {(2025, 5): 4.0, (2025, 6): 8.0},  # never cleared
    }
    rs.grade_tracked_recs(recs, weekly_fp, lambda _epoch: (2025, 5))
    assert recs[0].status == "CORRECT"  # A (18) > B (10)
    assert recs[1].status == "INCORRECT"  # A (18) < C (25)
    assert recs[2].status == "HIT"  # D hit 15 post-claim
    assert recs[3].status == "MISS"  # E capped at 8


def test_grade_tracked_recs_pending_when_week_or_name_unresolved() -> None:
    recs = [
        TrackedRec(
            "f1", "", "lineup", "", "PENDING", start="Ghost", sit="Nobody", made_at_epoch=1.0
        ),
        TrackedRec(
            "f2", "", "lineup", "", "PENDING", start="Player A", sit="Player B", made_at_epoch=2.0
        ),
    ]
    weekly_fp = {"player a": {(2025, 5): 18.0}, "player b": {(2025, 5): 10.0}}
    rs.grade_tracked_recs(recs, weekly_fp, lambda epoch: (2025, 5) if epoch == 1.0 else None)
    assert recs[0].status == "PENDING"  # names unmatched
    assert recs[1].status == "PENDING"  # week unresolved


def _schedule(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema={"season": pl.Int64, "week": pl.Int64, "gameday": pl.Utf8})


def test_week_resolver_maps_timestamp_and_rejects_offseason(monkeypatch) -> None:
    # Two-season schedule: a 2024 final week must not swallow the 2025 off-season gap.
    sched = _schedule(
        [
            {"season": 2024, "week": 17, "gameday": "2024-12-28"},
            {"season": 2025, "week": 1, "gameday": "2025-09-04"},
            {"season": 2025, "week": 2, "gameday": "2025-09-11"},
        ]
    )
    import sleeper_ffm.nflverse.loader as loader

    monkeypatch.setattr(loader, "load_schedules", lambda seasons=None, force=False: sched)
    resolve = rs._build_week_resolver([2024, 2025])

    def epoch(date: str) -> float:
        return dt.datetime.fromisoformat(f"{date}T18:00:00+00:00").timestamp()

    assert resolve(epoch("2025-09-10")) == (2025, 2)  # Wednesday before Thursday kickoff
    assert resolve(epoch("2025-09-06")) == (2025, 1)
    assert resolve(epoch("2025-07-15")) is None  # dead off-season, not 2024 wk17
    assert resolve(epoch("2024-01-01")) is None  # before the whole schedule
