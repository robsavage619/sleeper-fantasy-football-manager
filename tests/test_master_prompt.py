"""Master briefing composer — deterministic unit tests (no network calls)."""

from __future__ import annotations

from sleeper_ffm.api.routers.findings import MasterDocument
from sleeper_ffm.prompts.master import (
    MASTER_SCHEMA,
    BriefingContext,
    build_master_briefing,
)


def _context() -> BriefingContext:
    return BriefingContext(
        league_state="Season 2026, Week 1 (OFF).",
        my_roster="Starters:\n  QB  Somebody",
        saber_summary="Roster 2 (me): luck +0.10, lineup eff 92.0%, FAAB left 400.",
        intel_feed="  [WATCH] INJURY Somebody (WR ATL) — Questionable.",
        trade_offers="  [HIGH impact | FIT 90 OWNER-HISTORY] send Herbert for an RB.",
        trade_candidates="  Rival: CONTENDER — send X for Y.",
        waiver_candidates="  WR  Some Guy  FA  +50 adds",
        draft_context="(no active draft — off-season or draft complete)",
        prospect_context="Flag any rookie worth a scouting dive.",
        lineup_questions="This week's matchup:\n(off-season — no matchup)",
    )


def test_build_is_deterministic() -> None:
    ctx = _context()
    a = build_master_briefing(ctx, generated_at="2026-07-13T00:00:00+00:00")
    b = build_master_briefing(ctx, generated_at="2026-07-13T00:00:00+00:00")
    assert a == b


def test_timestamp_is_embedded() -> None:
    out = build_master_briefing(_context(), generated_at="2026-07-13T12:34:56+00:00")
    assert "2026-07-13T12:34:56+00:00" in out


def test_all_sections_present() -> None:
    ctx = _context()
    out = build_master_briefing(ctx, generated_at="t")
    for header in (
        "## League State",
        "## My Roster",
        "## Roster Sabermetrics",
        "## Trade Candidates",
        "## Waiver Candidates",
        "## Draft Context",
        "## Prospect Context",
        "## Lineup Questions",
    ):
        assert header in out
    assert ctx.saber_summary in out
    assert ctx.trade_candidates in out


def test_every_schema_key_appears_in_output_contract() -> None:
    out = build_master_briefing(_context(), generated_at="t")
    for key in MASTER_SCHEMA:
        assert f'"{key}"' in out


def test_schema_keys_match_bulk_document_fields() -> None:
    """The advertised schema keys must equal the fields /findings/bulk accepts."""
    assert set(MASTER_SCHEMA) == set(MasterDocument.model_fields)


def test_consolidated_analyses_are_in_the_single_prompt() -> None:
    """The formerly-separate /ai/* analyses are now tasks in the one master prompt."""
    out = build_master_briefing(_context(), generated_at="t")
    assert "## Rival Dossiers" in out  # per-rival exploit context, folded in
    for key in ("trade_plan", "market_edge", "waiver_plan", "owner_dossiers"):
        assert key in MASTER_SCHEMA
        assert f'"{key}"' in out  # appears in the output contract
    # The task enumerates them so the LLM produces each in the single run.
    assert "franchise BUY/SELL/HOLD posture" in out
    assert "one exploit plan per rival" in out
