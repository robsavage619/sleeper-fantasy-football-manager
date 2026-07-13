"""Multi-source prospect scouting report — assembler + derived-signal tests.

Network sources (FantasyCalc, nflverse combine) are monkeypatched so the tests
are hermetic and fast. The owner dossier reads from the repo's cached Sleeper
data, matching the rest of the suite.
"""

from __future__ import annotations

import pytest

from sleeper_ffm.model import prospect_report as pr


@pytest.fixture(autouse=True)
def _no_cfbd_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CFBD_API_KEY", raising=False)


def _patch_market(monkeypatch: pytest.MonkeyPatch, record: dict | None) -> None:
    full = {"999": record} if record else {}
    monkeypatch.setattr("sleeper_ffm.market.fantasycalc.fetch_full", lambda: full)


def _patch_combine(monkeypatch: pytest.MonkeyPatch, record: dict | None) -> None:
    monkeypatch.setattr(
        "sleeper_ffm.nflverse.combine.combine_for", lambda name, position, year: record
    )


@pytest.fixture(autouse=True)
def _no_college_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the college loader off the network by default; tests opt in."""
    monkeypatch.setattr("sleeper_ffm.college.cfb_box.college_history", lambda name, year: [])


_RICH_MARKET = {
    "value": 4832,
    "overall_rank": 20,
    "position_rank": 9,
    "tier": 11,
    "trend_30day": 120,
    "adp": None,
    "roster_pct": 0.99,
    "trade_frequency": 0.014,
    "volatility": 0,
    "volatility_pct": 0,
    "redraft_value": 3965,
    "redraft_dynasty_diff": -867,
    "draft_year": 2025,
    "draft_round": 1,
    "draft_pick": 8,
    "height": 77,
    "weight": 212,
    "college": "Arizona",
    "team": "CAR",
    "age": 22.0,
    "years_exp": 1,
}

_RICH_COMBINE = {
    "height_in": 76,
    "weight": 212,
    "forty": 4.44,
    "vertical": 38.5,
    "bench": None,
    "broad_jump": 127,
    "cone": None,
    "shuttle": None,
    "draft_round": 1,
    "draft_ovr": 8,
    "draft_team": "CAR",
    "school": "Arizona",
    "position": "WR",
    "speed_score": 106.0,
    "athletic_grade": "GOOD",
}


# ---- timeline + capital helpers ----


def test_player_timeline_ascending() -> None:
    assert pr._player_timeline({"value": 5000, "redraft_value": 3000}) == "ASCENDING"


def test_player_timeline_win_now() -> None:
    assert pr._player_timeline({"value": 3000, "redraft_value": 4000}) == "WIN-NOW"


def test_draft_capital_tier() -> None:
    assert pr._draft_capital_tier(1) == "PREMIUM"
    assert pr._draft_capital_tier(2) == "DAY 2"
    assert pr._draft_capital_tier(5) == "DAY 3"
    assert pr._draft_capital_tier(None) is None


def test_timeline_verdict_aligned_for_builder() -> None:
    assert pr._timeline_verdict("ASCENDING", "ASCENDING").startswith("ALIGNED")


def test_timeline_verdict_off_for_builder_win_now() -> None:
    assert pr._timeline_verdict("WIN-NOW", "ASCENDING").startswith("OFF-TIMELINE")


# ---- full assembler ----


def test_rich_report_is_full_quality(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_market(monkeypatch, _RICH_MARKET)
    _patch_combine(monkeypatch, _RICH_COMBINE)
    r = pr.build_scouting_report(
        name="Tetairoa McMillan",
        position="WR",
        college="Arizona",
        year=2025,
        age=22.0,
        player_id="999",
        dynasty_prospect_score=85.2,
    )
    assert r["data_quality"] == "FULL"
    assert "FantasyCalc" in r["sources_used"]
    assert r["market"]["position_rank"] == 9
    assert r["draft_capital"]["capital_tier"] == "PREMIUM"
    assert r["athleticism"]["athletic_grade"] == "GOOD"


def test_rich_report_signals_lead_with_capital(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_market(monkeypatch, _RICH_MARKET)
    _patch_combine(monkeypatch, _RICH_COMBINE)
    r = pr.build_scouting_report(
        name="Tetairoa McMillan",
        position="WR",
        college="Arizona",
        year=2025,
        age=22.0,
        player_id="999",
    )
    labels = [s["label"] for s in r["signals"]]
    assert any("draft capital" in label for label in labels)
    assert any("Market rising" in label for label in labels)


def test_unmatched_player_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_market(monkeypatch, None)
    _patch_combine(monkeypatch, None)
    r = pr.build_scouting_report(
        name="Nobody Prospect",
        position="WR",
        college="Nowhere",
        year=2025,
        age=23.0,
        player_id=None,
    )
    assert r["data_quality"] == "DEGRADED"
    assert r["market"] is None
    assert r["draft_capital"] is None
    assert any("FantasyCalc" in w for w in r["warnings"])


def test_market_only_is_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_market(monkeypatch, _RICH_MARKET)
    _patch_combine(monkeypatch, None)
    r = pr.build_scouting_report(
        name="Someone",
        position="WR",
        college="State",
        year=2025,
        age=22.0,
        player_id="999",
    )
    assert r["data_quality"] == "PARTIAL"


# ---- prompt ----


def test_scouting_prompt_packs_all_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_market(monkeypatch, _RICH_MARKET)
    _patch_combine(monkeypatch, _RICH_COMBINE)
    prompt = pr.build_scouting_prompt(
        name="Tetairoa McMillan",
        position="WR",
        college="Arizona",
        year=2025,
        age=22.0,
        player_id="999",
        dynasty_prospect_score=85.2,
    )
    assert "Market Consensus" in prompt
    assert "NFL Draft Capital" in prompt
    assert "Athletic Profile" in prompt
    assert "Search the web first" in prompt
    assert "sffm finding prospect_scout" in prompt
