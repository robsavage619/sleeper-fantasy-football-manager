"""Single master briefing composer for the one-prompt AI GM update.

Composes the existing per-surface prompt builders (narrative, trade angles,
waiver, draft, prospect, lineup) into ONE structured briefing and instructs
Claude Code to answer with exactly ONE JSON document.

Two layers:
    * ``build_master_briefing`` — PURE and deterministic: given a
      :class:`BriefingContext` and a timestamp string, it renders the briefing.
      No clock, no network — fully testable.
    * ``gather_briefing_context`` — the live glue that pulls Sleeper/nflverse
      data via the existing builders and packs a :class:`BriefingContext`. Each
      source is wrapped so one failure degrades a single section, not the whole
      briefing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sleeper_ffm.config import MY_ROSTER_ID

log = logging.getLogger(__name__)

# Canonical schema advertised at GET /ai/briefing. Keys MUST match the fields
# accepted by POST /findings/bulk (see api/routers/findings.py::MasterDocument).
MASTER_SCHEMA: dict[str, str] = {
    "narrative": "string — league-wide state of the union / weekly outlook (1-3 paragraphs)",
    "trade_recs": (
        "array of objects — each {partner, send, receive, rationale, urgency:LOW|MED|HIGH}"
    ),
    "waiver_recs": "array of objects — each {player, faab_bid, drop, rationale}",
    "draft_recs": "array of objects — each {pick, alternatives, rationale}",
    "prospect_notes": "array of objects — each {name, verdict, rationale}",
    "lineup_recs": "array of objects — each {start, sit, rationale}",
    "generated_at": "string — ISO-8601 timestamp you stamp when you answer",
    "data_quality_ack": "string — explicitly acknowledge any stale/missing data you relied on",
}


@dataclass
class BriefingContext:
    """Pre-rendered section text for the master briefing (all strings, no live objects)."""

    league_state: str
    my_roster: str
    saber_summary: str
    intel_feed: str
    trade_offers: str
    trade_candidates: str
    waiver_candidates: str
    draft_context: str
    prospect_context: str
    lineup_questions: str


def build_master_briefing(context: BriefingContext, generated_at: str) -> str:
    """Render the single master briefing prompt from pre-built section text.

    Deterministic: identical ``context`` + ``generated_at`` always yield the same
    string. The timestamp is injected (never read from the clock) so the builder
    stays pure and testable.

    Args:
        context: Section text assembled by :func:`gather_briefing_context`.
        generated_at: ISO-8601 timestamp to embed as the briefing's issue time.

    Returns:
        A structured prompt instructing Claude Code to return exactly one JSON document.
    """
    schema_lines = "\n".join(f'  "{key}": {desc}' for key, desc in MASTER_SCHEMA.items())
    return f"""# Dynasty War Room — Master Briefing
Issued: {generated_at}

You are the AI General Manager for this dynasty fantasy football roster. Below is
the entire state of the franchise in one briefing. Reason over ALL of it, then
answer with ONE JSON document (schema at the bottom) and NOTHING ELSE.

## League State
{context.league_state}

## My Roster
{context.my_roster}

## Roster Sabermetrics (GM performance signals)
{context.saber_summary}

## Real-World Intel (injuries, depth-chart risk, opportunity, league moves)
Factor this into every call: don't chase or hold an injured/buried player, and
jump waiver opportunities before the herd.
{context.intel_feed}

## Realistic Trade Offers (acceptance-model, grounded in how THIS league trades)
These are engine-built, value-balanced offers: they trade surplus depth (never a
cornerstone), pay the market premium a coveted position commands here, and only
send a QB to a QB-needy partner. Prefer these over the raw angles below.
{context.trade_offers}

## Trade Candidates (raw positional angles — directional only, not value-balanced)
{context.trade_candidates}

## Waiver Candidates
{context.waiver_candidates}

## Draft Context
{context.draft_context}

## Prospect Context
{context.prospect_context}

## Lineup Questions
{context.lineup_questions}

---
## Your Task
Produce a single GM update covering every surface above:
1. A league-wide narrative: where does this franchise stand and what is the plan.
2. Concrete trade recommendations grounded in the positional angles.
3. Waiver moves with FAAB bids ($500 budget) and the drop.
4. Draft recommendations (if a draft is active or approaching).
5. Prospect notes for any names worth tracking.
6. Lineup start/sit calls (in-season only).

Acknowledge, in `data_quality_ack`, any section that was empty, stale, or degraded
so the reader knows what you could NOT ground your reasoning in.

## Output Contract — return EXACTLY this JSON object and nothing else
{{
{schema_lines}
}}

Empty arrays are valid when a surface has no action this cycle. Do not wrap the
JSON in prose or markdown fences. Do not invent data that is absent above.
"""


def gather_briefing_context(my_roster_id: int = MY_ROSTER_ID) -> BriefingContext:
    """Assemble live section text by composing the existing per-surface builders.

    Each source is wrapped independently: a failure degrades one section to a
    visible placeholder rather than aborting the whole briefing.

    Args:
        my_roster_id: Roster ID to summarize sabermetrics for.

    Returns:
        A :class:`BriefingContext` with every section populated (or flagged degraded).
    """
    league_state, my_roster, trade_candidates, waiver_candidates, lineup_questions = (
        _from_narrative()
    )
    return BriefingContext(
        league_state=league_state,
        my_roster=my_roster,
        saber_summary=_saber_summary(my_roster_id),
        intel_feed=_intel_feed(my_roster_id),
        trade_offers=_trade_offers(),
        trade_candidates=trade_candidates,
        waiver_candidates=waiver_candidates,
        draft_context=_draft_context(),
        prospect_context=_prospect_context(),
        lineup_questions=lineup_questions,
    )


def _intel_feed(my_roster_id: int) -> str:
    """Real-world status feed (injuries, depth, opportunity, league moves)."""
    try:
        from sleeper_ffm.model.news_feed import build_feed

        feed = build_feed(my_roster_id)
    except Exception as exc:
        log.warning("master: intel feed unavailable: %s", exc)
        return "(degraded — intel feed unavailable)"

    lines: list[str] = []
    for a in feed.roster_alerts[:12]:
        lines.append(f"  [{a.severity}] {a.kind} {a.name} ({a.position} {a.team}) — {a.detail}")
    for a in feed.opportunities[:6]:
        lines.append(f"  [OPP] {a.name} ({a.position} {a.team}) — {a.detail}")
    for m in feed.league_moves[:6]:
        who = "you" if m.get("involves_me") else f"roster {m.get('roster_ids')}"
        adds = ", ".join(m.get("adds") or []) or "—"
        drops = ", ".join(m.get("drops") or []) or "—"
        lines.append(f"  [MOVE wk{m.get('week')}] {who} {m.get('type')}: +{adds} / -{drops}")
    body = "\n".join(lines) if lines else "  (no active alerts)"
    return f"{feed.generated_note}\n{body}"


def _trade_offers(top: int = 6) -> str:
    """Top acceptance-model offers from the grounded trade engine."""
    try:
        from sleeper_ffm.model.trade_acceptance import recommend_trade_offers

        offers = recommend_trade_offers(top=top)
    except Exception as exc:
        log.warning("master: trade offers unavailable: %s", exc)
        return "(degraded — trade engine unavailable)"

    if not offers:
        return "  (no acceptance-model offers this cycle)"

    lines: list[str] = []
    for offer in offers:
        give = " + ".join(a.label for a in offer.give)
        receive = " + ".join(a.label for a in offer.receive)
        lines.append(
            f"  [{offer.impact_label} impact | FIT {offer.acceptance_score} {offer.calibration}] "
            f"send {give} (~{offer.give_value:.0f}) for {receive} (~{offer.receive_value:.0f}) "
            f"— {offer.rationale}"
        )
    return "\n".join(lines)


def _from_narrative() -> tuple[str, str, str, str, str]:
    """Derive league/roster/trade/waiver/lineup sections from the narrative builder."""
    try:
        from sleeper_ffm.prompts.narrative import build_narrative_context

        ctx = build_narrative_context()
    except Exception as exc:
        log.warning("master: narrative context unavailable: %s", exc)
        degraded = "(degraded — narrative context unavailable)"
        return (degraded, degraded, degraded, degraded, degraded)

    sections = ctx.sections
    league_state = f"Season {ctx.season}, Week {ctx.week} ({ctx.season_type.upper()})."
    roster_lines = sections.get("starters") or []
    bench = sections.get("bench") or []
    my_roster = "Starters:\n" + ("\n".join(roster_lines) if roster_lines else "  (none)")
    if bench:
        my_roster += "\nBench: " + ", ".join(bench)

    trade_lines = sections.get("trade_angles") or []
    trade_candidates = "\n".join(trade_lines) if trade_lines else "  (no valuation-backed fits)"

    waiver_lines = sections.get("waiver_adds") or []
    waiver_candidates = "\n".join(waiver_lines) if waiver_lines else "  (no trending adds)"

    matchup = sections.get("matchup") or "(off-season — no matchup)"
    lineup_questions = f"This week's matchup:\n{matchup}"
    return league_state, my_roster, trade_candidates, waiver_candidates, lineup_questions


def _saber_summary(my_roster_id: int) -> str:
    """One-line GM sabermetric summary for my roster (luck, lineup efficiency, FAAB).

    ``gm_metrics`` is loaded dynamically: it ships in a sibling analytics
    workstream and may not be present in every checkout. Absence degrades this
    one section rather than breaking the briefing.
    """
    try:
        import importlib

        build_gm_metrics = importlib.import_module("sleeper_ffm.model.gm_metrics").build_gm_metrics
        metrics = build_gm_metrics()
    except Exception as exc:
        log.warning("master: gm_metrics unavailable: %s", exc)
        return "(degraded — GM sabermetrics unavailable)"

    mine = next((m for m in metrics if m.roster_id == my_roster_id), None)
    if mine is None:
        return f"(no GM metrics for roster {my_roster_id})"

    luck = mine.luck.get("luck_index")
    eff = mine.lineup_efficiency.get("mean_efficiency")
    faab_left = mine.faab.get("remaining")
    luck_str = f"luck index {luck:+.2f}" if isinstance(luck, (int, float)) else "luck index n/a"
    eff_str = (
        f"lineup efficiency {eff:.1%}" if isinstance(eff, (int, float)) else "lineup efficiency n/a"
    )
    faab_str = f"FAAB remaining {faab_left}" if faab_left is not None else "FAAB n/a"
    parts = [luck_str, eff_str, faab_str]
    return f"Roster {my_roster_id} ({mine.display_name or 'me'}): " + ", ".join(parts) + "."


def _draft_context() -> str:
    """Live draft board summary when a draft is active, else an off-season note."""
    try:
        from sleeper_ffm.draft.assistant import sync_board

        board = sync_board()
    except Exception as exc:
        log.info("master: no active draft board (%s)", exc)
        return "(no active draft — off-season or draft complete)"

    if board.is_complete():
        return "(draft complete — no live picks)"
    return (
        f"Live draft: pick {board.current_pick_no}/{board.total_picks} "
        f"(round {board.current_round}), {board.picks_until_my_turn} picks until my turn."
    )


def _prospect_context() -> str:
    """Short prospect-watch pointer (deep dives run per-prospect via /prospects)."""
    return (
        "Deep prospect scouting runs per-player via the prospect surface. Flag any rookie "
        "or stash worth a full scouting dive in `prospect_notes` with a one-line verdict."
    )
