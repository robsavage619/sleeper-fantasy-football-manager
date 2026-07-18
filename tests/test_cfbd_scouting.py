"""CFBD loader degrade-path tests — pure college helpers, no network calls."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_cfbd_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CFBD_API_KEY", raising=False)


def test_fetch_season_history_empty_without_key() -> None:
    from sleeper_ffm.cfbd.loader import fetch_season_history

    assert fetch_season_history("Test Prospect", "WR", 2025) == []


def test_fetch_bio_none_without_key() -> None:
    from sleeper_ffm.cfbd.loader import fetch_bio

    assert fetch_bio("Test Prospect") is None


class _FakeClient:
    def __init__(self, dump: dict) -> None:
        self._dump = dump

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def players(self) -> dict:
        return self._dump


def test_fallback_rejects_stale_and_misindexed_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Sleeper fallback board must keep real incoming rookies and drop stale entries.

    Sleeper keeps retired/historical players in the dump with years_exp 0, an
    active=False flag, and a 9_999_999 search_rank sentinel — all three leaked onto the
    rookie board when the only gate was years_exp. This locks the multi-gate filter.
    """
    import sleeper_ffm.sleeper.client as client_mod
    from sleeper_ffm.cfbd.loader import _fallback_sleeper_prospects

    dump = {
        # real 2026 rookies — must survive
        "real_rb": {"position": "RB", "years_exp": 0, "age": 21, "active": True,
                    "search_rank": 15, "full_name": "Real Rookie", "team": "ARI"},
        "real_wr": {"position": "WR", "years_exp": 0, "age": 22, "active": True,
                    "search_rank": 61, "full_name": "Second Rookie", "team": "TEN"},
        # real DEEP rookie: signed UDFA carries the 9_999_999 sentinel rank but has a team —
        # must survive (the sentinel is NOT a valid discriminator).
        "deep_udfa": {"position": "WR", "years_exp": 0, "age": 24, "active": True,
                      "search_rank": 9999999, "full_name": "Deep Udfa", "team": "LV"},
        # retired/coach: active False, no team — must drop
        "retired": {"position": "RB", "years_exp": 0, "age": None, "active": False,
                    "search_rank": 9999999, "full_name": "Retired Coach", "team": None},
        # active but teamless washed player — must drop on the team gate
        "no_team": {"position": "WR", "years_exp": 0, "age": 25, "active": True,
                    "search_rank": 999, "full_name": "Teamless Washout", "team": None},
        # too old to be an incoming rookie — must drop
        "too_old": {"position": "WR", "years_exp": 0, "age": 29, "active": True,
                    "search_rank": 120, "full_name": "Old Vet", "team": "SF"},
        # veteran by experience — must drop (existing gate)
        "veteran": {"position": "QB", "years_exp": 4, "age": 26, "active": True,
                    "search_rank": 40, "full_name": "Established Vet", "team": "KC"},
    }
    monkeypatch.setattr(client_mod, "SleeperClient", lambda *a, **k: _FakeClient(dump))

    names = {p.name for p in _fallback_sleeper_prospects(2026, top=50)}
    assert names == {"Real Rookie", "Second Rookie", "Deep Udfa"}
