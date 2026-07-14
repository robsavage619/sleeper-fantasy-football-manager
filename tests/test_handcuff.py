"""Tests for the handcuff/leverage helpers (pure logic — no network)."""

from __future__ import annotations

from sleeper_ffm.model.handcuff import backup_of, classify_status, order_depth


def _rows() -> list[dict]:
    return [
        {"team": "KC", "position": "RB", "rank": 1, "sid": "star"},
        {"team": "KC", "position": "RB", "rank": 2, "sid": "backup"},
        {"team": "KC", "position": "RB", "rank": 3, "sid": "deep"},
        {"team": "KC", "position": "WR", "rank": 1, "sid": "wr1"},
    ]


def test_order_depth_sorts_by_rank() -> None:
    order = order_depth(_rows())
    assert order[("KC", "RB")] == ["star", "backup", "deep"]
    assert order[("KC", "WR")] == ["wr1"]


def test_order_depth_skips_unmapped() -> None:
    rows = [{"team": "KC", "position": "RB", "rank": 1, "sid": None}]
    assert order_depth(rows) == {}


def test_backup_of_returns_next_in_chain() -> None:
    order = order_depth(_rows())
    assert backup_of(order, "KC", "RB", "star") == "backup"
    assert backup_of(order, "KC", "RB", "backup") == "deep"


def test_backup_of_none_when_last_or_absent() -> None:
    order = order_depth(_rows())
    assert backup_of(order, "KC", "RB", "deep") is None
    assert backup_of(order, "KC", "RB", "ghost") is None
    assert backup_of(order, "KC", "WR", "wr1") is None


def test_classify_status() -> None:
    assert classify_status("backup", "me") == "SECURED"
    assert classify_status("backup", "roster:5") == "EXPOSED"
    assert classify_status("backup", "free_agent") == "EXPOSED"
    assert classify_status(None, "free_agent") == "NO_BACKUP"
