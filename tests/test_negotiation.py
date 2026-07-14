"""Tests for the negotiation copilot pure helpers (no network)."""

from __future__ import annotations

from types import SimpleNamespace

from sleeper_ffm.prompts.negotiation import _needs_and_surplus, negotiation_angles


def test_angles_lead_with_youth_for_rebuilder() -> None:
    pts = negotiation_angles("Youth-hoarding rebuilder", "REBUILD", "RB")
    assert any("youth" in p.lower() for p in pts)
    assert any("rebuild" in p.lower() for p in pts)


def test_angles_emphasize_starters_for_contender() -> None:
    pts = negotiation_angles("Win-now star collector", "WIN-NOW", "WR")
    assert any("immediate" in p.lower() or "starting" in p.lower() for p in pts)
    assert any("contending" in p.lower() for p in pts)


def test_angles_always_include_scarcity_anchor() -> None:
    pts = negotiation_angles("", "", "TE")
    assert any("TE" in p and "scarcity" in p.lower() for p in pts)


def test_needs_and_surplus_split_by_rank() -> None:
    ranks = [
        SimpleNamespace(position="RB", rank=9, of=10),  # weak → need
        SimpleNamespace(position="WR", rank=1, of=10),  # strong → surplus
        SimpleNamespace(position="TE", rank=5, of=10),  # middle → neither
    ]
    needs, surplus = _needs_and_surplus(ranks)
    assert needs == ["RB"]
    assert surplus == ["WR"]


def test_needs_and_surplus_accepts_dicts() -> None:
    ranks = [{"position": "QB", "rank": 10, "of": 10}]
    needs, surplus = _needs_and_surplus(ranks)
    assert needs == ["QB"]
    assert surplus == []
