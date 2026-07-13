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
