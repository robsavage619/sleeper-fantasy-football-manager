"""Focused agent-reasoning prompts for decision surfaces beyond the master briefing.

The master briefing (``prompts.master``) reasons over the whole franchise in one
pass. These surfaces are the opposite: each takes ONE signal-rich area that today
terminates at raw numbers (owner dossiers, the mispricing/regression/opponent-
adjusted board trio, waivers + wire, trade offers + season posture) and wraps it in
a focused prompt so an agent (Claude Code) can reason deeply and post a typed finding
back — the same contract as ``/ai/briefing`` (a prompt ending in a JSON schema).

Context is composed from the master briefing's section helpers so there is one
source of truth per engine: this module never re-plumbs an engine the briefing
already renders. Every builder degrades the same way the briefing does — a dead
engine yields a visible ``(degraded — …)`` placeholder, never a raise.
"""

from __future__ import annotations

import logging

from sleeper_ffm.config import MY_ROSTER_ID
from sleeper_ffm.prompts import master

log = logging.getLogger(__name__)


# ---- output contracts (mirror the /ai/briefing {prompt, schema} shape) -------------

DOSSIER_SCHEMA: dict[str, str] = {
    "target": "string — roster_id + display_name of the manager being scouted",
    "exploit_plan": (
        "string — 1-2 paragraphs: how to win trades against THIS manager given their "
        "contention window, roster holes, positional surplus, and pick capital"
    ),
    "angles": (
        "array of objects — each {send, receive, rationale, urgency:LOW|MED|HIGH}: "
        "concrete offers to pitch them, framed around what they need and will part with"
    ),
    "watch_items": "array of strings — assets of theirs to monitor or pry loose later",
    "generated_at": "string — ISO-8601 timestamp you stamp when you answer",
    "data_quality_ack": "string — acknowledge any stale/missing data you relied on",
}

MARKET_EDGE_SCHEMA: dict[str, str] = {
    "buys": (
        "array of objects — each {player, thesis, target_partner}: players to ACQUIRE "
        "(underpriced for our scoring, unlucky TD regression, or schedule-deflated)"
    ),
    "sells": (
        "array of objects — each {player, thesis, target_partner}: players to MOVE "
        "(overpriced vs our rules, rode TD variance up, or schedule-inflated)"
    ),
    "reconciliations": (
        "string — where the three boards disagree on a player (e.g. sell-high on "
        "regression but buy on mispricing) and how you resolve the conflict"
    ),
    "generated_at": "string — ISO-8601 timestamp you stamp when you answer",
    "data_quality_ack": "string — acknowledge any stale/missing data you relied on",
}

WAIVER_PLAN_SCHEMA: dict[str, str] = {
    "waiver_recs": (
        "array of objects — each {player, faab_bid, drop, tier, rationale}; faab_bid is a "
        "JSON number of dollars against a $500 budget (never a string or $-prefixed); tier "
        "is PRIORITY|SPECULATIVE|DART"
    ),
    "holds": "array of strings — trending names to deliberately pass on, and why",
    "generated_at": "string — ISO-8601 timestamp you stamp when you answer",
    "data_quality_ack": "string — acknowledge any stale/missing data you relied on",
}

TRADE_PLAN_SCHEMA: dict[str, str] = {
    "posture": "string — BUY | SELL | HOLD, given my title equity and contention window",
    "plan": "string — 1-2 paragraphs: franchise posture and what to target vs shed",
    "trade_recs": (
        "array of objects — each {partner, send, receive, rationale, urgency:LOW|MED|HIGH}"
    ),
    "sequencing": "string — the order to run the moves and any dependencies between them",
    "generated_at": "string — ISO-8601 timestamp you stamp when you answer",
    "data_quality_ack": "string — acknowledge any stale/missing data you relied on",
}


def _schema_block(schema: dict[str, str]) -> str:
    """Render a schema dict the same way the master briefing does."""
    return "{\n" + "\n".join(f'  "{key}": {desc}' for key, desc in schema.items()) + "\n}"


def _wrap(
    title: str,
    intro: str,
    sections: list[tuple[str, str]],
    task: str,
    schema: dict[str, str],
    kind: str,
) -> str:
    """Assemble a focused reasoning prompt: intro → context sections → task → contract."""
    body = "\n\n".join(f"## {heading}\n{text}" for heading, text in sections)
    return (
        f"# {title}\n{intro}\n\n{body}\n\n---\n## Your Task\n{task}\n\n"
        "## Output Contract — return EXACTLY this JSON object and nothing else\n"
        f"{_schema_block(schema)}\n\n"
        "Empty arrays are valid when a surface has no action. Do not wrap the JSON in prose "
        f"or markdown fences. Post it back via POST /findings/typed with kind `{kind}`. "
        "Do not invent data absent from the context above."
    )


# ---- dossier ------------------------------------------------------------------------


def _fmt_dossier_player(p: dict) -> str:
    return (
        f"{p.get('name', '?')} ({p.get('position', '?')} {p.get('team', '?')}, "
        f"{p.get('dynasty_value', 0):.0f})"
    )


def _dossier_section(roster_id: int) -> str:
    """Render one rival's full dossier (holdings, needs, window, picks) for reasoning.

    Rendering runs inside the degrade guard so a dataclass field drift downgrades this
    one section to a placeholder rather than 500-ing the whole prompt endpoint.
    """
    try:
        from sleeper_ffm.config import DEFAULT_VALUE_SEASON
        from sleeper_ffm.model.owner_dossier import build_dossier

        d = build_dossier(roster_id, DEFAULT_VALUE_SEASON)

        pos_val = ", ".join(f"{p.position} {p.value:.0f}" for p in d.value_by_position)
        ranks = ", ".join(
            f"{r.position} #{r.rank}/{r.of} ({r.tier})" for r in d.position_ranks
        )
        ranked = sorted(d.players, key=lambda x: -float(x.get("dynasty_value", 0) or 0))
        top_players = ", ".join(_fmt_dossier_player(p) for p in ranked[:10])
        picks = (
            ", ".join(f"{p.get('season', '?')} R{p.get('round', '?')}" for p in d.picks_owned)
            or "none tracked"
        )
        return (
            f"Manager: roster {d.roster_id} ({d.display_name}). Value rank {d.value_rank}, total "
            f"dynasty value {d.total_dynasty_value:.0f}, avg age {d.avg_age:.1f} "
            f"(starters {d.avg_starter_age:.1f}), {d.player_count} players.\n"
            f"Contention: {d.contention.window} — {d.contention.label}. {d.contention.rationale}\n"
            f"Value by position: {pos_val}\nPositional ranks (low rank = strength, high = need): "
            f"{ranks}\nTop holdings: {top_players}\nFuture picks owned: {picks}"
        )
    except Exception as exc:
        log.warning("surfaces: dossier unavailable for roster %s: %s", roster_id, exc)
        return f"(degraded — dossier for roster {roster_id} unavailable)"


def build_dossier_prompt(roster_id: int) -> str:
    """Prompt: how to win trades against one specific manager."""
    return _wrap(
        title="Owner Dossier — Exploit Plan",
        intro=(
            "You are the AI GM scouting ONE rival manager to find the trades you can win "
            "against them. Reason over their roster construction, window, and holes, then "
            "produce concrete offers framed around what they need and will part with."
        ),
        sections=[
            ("Target Manager", _dossier_section(roster_id)),
            ("My Roster", master._from_narrative()[1]),
            ("My Sabermetrics", master._saber_summary(MY_ROSTER_ID)),
            ("League Contention Windows", master._contention_section(MY_ROSTER_ID)),
            (
                "Acceptance-Model Offers (grounded in how this league trades)",
                master._trade_offers(),
            ),
        ],
        task=(
            "Build the plan to beat this manager in a trade: name their exploitable holes, "
            "then give specific offers that fit both rosters' windows. Rank angles by "
            "likelihood-to-close, not just value."
        ),
        schema=DOSSIER_SCHEMA,
        kind="owner_dossier",
    )


# ---- market edges -------------------------------------------------------------------


def _opponent_adjusted_section(top: int = 8) -> str:
    """Players whose raw production was most inflated/deflated by schedule."""
    try:
        from sleeper_ffm.model.opponent_adjusted import build_opponent_adjusted

        board = build_opponent_adjusted(top=top)
    except Exception as exc:
        log.warning("surfaces: opponent-adjusted unavailable: %s", exc)
        return "(degraded — opponent-adjusted board unavailable)"

    def _line(e: object) -> str:
        return (
            f"    {e.name} ({e.position} {e.team}): raw {e.raw_fp:.0f} → adj {e.adjusted_fp:.0f} "
            f"(schedule luck {e.schedule_luck:+.0f})"
        )

    lines = ["  INFLATED by soft schedules (sell-high risk):"]
    lines += [_line(e) for e in board.softest_schedule] or ["    (none)"]
    lines.append("  DEFLATED by tough schedules (buy-low upside):")
    lines += [_line(e) for e in board.toughest_schedule] or ["    (none)"]
    return "\n".join(lines)


def build_market_edges_prompt() -> str:
    """Prompt: reconcile mispricing + regression + opponent-adjusted into buy/sell theses."""
    return _wrap(
        title="Market Edges — Buy/Sell Theses",
        intro=(
            "You are the AI GM turning three market-inefficiency boards into a ranked buy/sell "
            "list. A player can show up on more than one board with conflicting signals — your "
            "job is to reconcile them into a defensible thesis, then name who to trade with."
        ),
        sections=[
            (
                "League-Specific Mispricing (our scoring vs generic PPR)",
                master._mispricing_section(),
            ),
            ("Regression Watch (TD-over-expected)", master._regression_section()),
            ("Opponent-Adjusted (schedule-neutral production)", _opponent_adjusted_section()),
            (
                "League Contention Windows (who buys/sells)",
                master._contention_section(MY_ROSTER_ID),
            ),
        ],
        task=(
            "Produce ranked BUY and SELL theses. For each, state the edge (which board(s) flag "
            "it and why), reconcile any conflict between boards, and name a realistic target "
            "partner given the contention windows."
        ),
        schema=MARKET_EDGE_SCHEMA,
        kind="market_edge",
    )


# ---- waivers + wire -----------------------------------------------------------------


def build_waiver_plan_prompt() -> str:
    """Prompt: a FAAB bid plan over trending adds + snap-share risers."""
    _, my_roster, _, waiver_candidates, _ = master._from_narrative()
    return _wrap(
        title="Waiver Plan — FAAB Bids & Drops",
        intro=(
            "You are the AI GM setting this week's waiver claims. Turn trending adds and "
            "snap-share risers into a concrete bid plan against a $500 FAAB budget: which "
            "claims, what to bid, who to drop, and which trending names to deliberately pass."
        ),
        sections=[
            ("Trending Waiver Candidates", waiver_candidates),
            (
                "Wire Early-Warning (snap-share risers, still available)",
                master._wire_watch_section(MY_ROSTER_ID),
            ),
            ("Handcuffs & Leverage (contingent value)", master._handcuff_section(MY_ROSTER_ID)),
            ("My Roster (for drop context)", my_roster),
            ("My Sabermetrics (FAAB remaining, etc.)", master._saber_summary(MY_ROSTER_ID)),
        ],
        task=(
            "Give a disciplined bid plan: rank claims by tier (PRIORITY/SPECULATIVE/DART), size "
            "each FAAB bid to the budget and the player's real role, justify every drop against "
            "the roster, and list the trending names you are choosing to pass on and why."
        ),
        schema=WAIVER_PLAN_SCHEMA,
        kind="waiver_plan",
    )


# ---- trade plan + season posture ----------------------------------------------------


def build_trade_plan_prompt() -> str:
    """Prompt: franchise buy/sell posture + sequenced trade plan."""
    _, my_roster, trade_candidates, _, _ = master._from_narrative()
    return _wrap(
        title="Trade Plan — Franchise Posture",
        intro=(
            "You are the AI GM setting the franchise's trade posture. Given where my title "
            "equity places me and my contention window, decide BUY/SELL/HOLD, then lay out a "
            "sequenced plan of specific offers — order matters when moves depend on each other."
        ),
        sections=[
            ("Title Equity (Monte-Carlo season sim)", master._title_equity_section(MY_ROSTER_ID)),
            ("League Contention Windows", master._contention_section(MY_ROSTER_ID)),
            ("Acceptance-Model Offers (grounded)", master._trade_offers()),
            ("Raw Positional Angles (directional)", trade_candidates),
            ("Handcuffs & Leverage", master._handcuff_section(MY_ROSTER_ID)),
            ("My Roster", my_roster),
            ("My Sabermetrics", master._saber_summary(MY_ROSTER_ID)),
        ],
        task=(
            "State the posture (BUY/SELL/HOLD) and defend it from the title-equity + window "
            "data. Then give a sequenced set of trade_recs — which to run first, what each "
            "unlocks, and the fallback if a partner declines."
        ),
        schema=TRADE_PLAN_SCHEMA,
        kind="trade_plan",
    )
