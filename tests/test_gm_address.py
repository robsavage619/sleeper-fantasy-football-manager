"""Tests for the GM weekly-address prompt builder (pure — no network)."""

from __future__ import annotations

from sleeper_ffm.prompts.gm_address import build_gm_address
from sleeper_ffm.prompts.master import BriefingContext


def _ctx() -> BriefingContext:
    return BriefingContext(
        league_state="Season 2026, Week 1 (PRE).",
        my_roster="Starters:\n  QB Guy",
        saber_summary="luck n/a",
        intel_feed="(no active alerts)",
        trade_offers="(none)",
        trade_candidates="(none)",
        waiver_candidates="(none)",
        draft_context="(off-season)",
        prospect_context="(none)",
        lineup_questions="(off-season)",
        title_equity="  1. roster 2: title 20%",
        contention="  roster 2 [WIN-NOW]",
        mispricing="BUY: Player X",
        regression="SELL-HIGH: Player Y",
    )


def test_address_is_deterministic() -> None:
    a = build_gm_address(_ctx(), generated_at="2026-07-14T00:00:00+00:00")
    b = build_gm_address(_ctx(), generated_at="2026-07-14T00:00:00+00:00")
    assert a == b


def test_address_embeds_context_and_voice() -> None:
    out = build_gm_address(_ctx(), generated_at="t")
    assert "State of the franchise" in out
    assert "title 20%" in out  # title equity flowed in
    assert "BUY: Player X" in out  # mispricing flowed in
    assert "gm_address" in out  # finding-post instruction present
