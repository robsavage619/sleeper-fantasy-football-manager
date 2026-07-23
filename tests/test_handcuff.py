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


def test_latest_depth_rows_uses_one_capture_per_team(monkeypatch) -> None:
    """Only the most recent capture may survive per team.

    The newer nflverse feed captures a depth chart several times a week. Stacking
    two captures together puts the same player at two ranks, which made the
    handcuff matcher pair a starter with himself.
    """
    import polars as pl

    from sleeper_ffm.model import handcuff as hc

    frame = pl.DataFrame(
        {
            "dt": ["2025-09-10T07:00:00Z"] * 2 + ["2025-09-17T07:00:00Z"] * 2,
            "club_code": ["ATL"] * 4,
            "depth_position": ["WR"] * 4,
            "depth_team": ["1", "2", "1", "2"],
            "gsis_id": ["g-old1", "g-old2", "g-new1", "g-new2"],
            "full_name": ["Stale One", "Stale Two", "Fresh One", "Fresh Two"],
            "week": [1, 1, 2, 2],
        }
    )
    monkeypatch.setattr(hc, "load_depth_charts", lambda **_k: frame)
    empty_id_map = pl.DataFrame(
        schema={"gsis_id": pl.Utf8, "sleeper_id": pl.Utf8},
    )
    monkeypatch.setattr(hc, "load_id_map", lambda: empty_id_map)

    rows = hc._latest_depth_rows(2025)
    assert sorted(r["name"] for r in rows) == ["Fresh One", "Fresh Two"]
    assert sorted(r["rank"] for r in rows) == [1, 2]
