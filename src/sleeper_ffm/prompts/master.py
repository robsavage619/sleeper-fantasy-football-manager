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
    "narrative": (
        "string — the GM's weekly column, 2-4 paragraphs. Not a terse status line: write "
        "the swaggering, numbers-literate 'State of the Franchise' address in the national "
        "war-room voice — where the franchise stands, the plan, one bold call, receipts "
        "included, no unearned hedging. This is meant to be read."
    ),
    "trade_recs": (
        "array of objects — each {partner, send, receive, rationale, urgency:LOW|MED|HIGH}"
    ),
    "waiver_recs": (
        "array of objects — each {player, faab_bid, drop, rationale}; "
        "faab_bid is a JSON number of dollars (e.g. 12), never a string or a $-prefixed value"
    ),
    "draft_recs": "array of objects — each {pick, alternatives, rationale}",
    "prospect_notes": "array of objects — each {name, verdict, rationale}",
    "lineup_recs": "array of objects — each {start, sit, rationale}",
    "trade_plan": (
        "object — franchise trade posture: {posture: BUY|SELL|HOLD, plan, "
        "trade_recs:[{partner,send,receive,rationale,urgency}], sequencing}"
    ),
    "market_edge": (
        "object — reconciled buy/sell board: {buys:[{player,thesis,target_partner}], "
        "sells:[{player,thesis,target_partner}], reconciliations}"
    ),
    "waiver_plan": (
        "object — disciplined FAAB plan: {waiver_recs:[{player,faab_bid,drop,tier,rationale}] "
        "with tier PRIORITY|SPECULATIVE|DART, holds:[names to pass on]}"
    ),
    "owner_dossiers": (
        "array of objects — one per rival manager: {target, exploit_plan, "
        "angles:[{send,receive,rationale,urgency}], watch_items}"
    ),
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
    # League-specific edge sections (default "" so older callers/tests stay valid).
    mispricing: str = ""
    roster_environment: str = ""
    schedule_outlook: str = ""
    title_equity: str = ""
    contention: str = ""
    regression: str = ""
    player_intel: str = ""
    handcuffs: str = ""
    wire_watch: str = ""
    early_claims: str = ""
    best_available: str = ""
    transaction_grades: str = ""
    rival_dossiers: str = ""
    track_record: str = ""
    data_freshness: str = ""


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

## GM Track Record (how your own past calls have graded out)
Your prior lineup and waiver recommendations, scored against what actually happened
(started player outscored the benched one; a waiver add cleared a startable week). Let
this calibrate your confidence: if a category's hit-rate is low or thin, hedge and say so
in `data_quality_ack`; if it's strong, you've earned the conviction. PENDING items aren't
failures — they just haven't played out yet.
{context.track_record}

## Data Freshness (what the engine knows is stale right now)
{context.data_freshness}

## Title Equity (Monte-Carlo season simulation)
Where this roster's raw strength places it in the league's title race. This is the
currency that should drive contend-vs-rebuild framing and how aggressively to buy/sell:
a high title share argues for pushing chips in now; a low one argues for accumulating.
{context.title_equity}

## Real-World Intel (injuries, depth-chart risk, opportunity, league moves)
Factor this into every call: don't chase or hold an injured/buried player, and
jump waiver opportunities before the herd.
{context.intel_feed}

## Transaction Grades (league moves graded on the curve)
Every completed trade and waiver claim in league history, letter-graded against every
other move made the same season — a waiver claim's grade weighs realized points against
its FAAB cost, a trade side's grade is realized points gained versus given up. Grades
marked SETTLING are too recent (<4 completed weeks) to trust yet. Use this to read
opponents: a manager whose grades lean low on trades is an easier partner; one who
crushes waivers is who you're racing to the wire.
{context.transaction_grades}

## Realistic Trade Offers (acceptance-model, grounded in how THIS league trades)
These are engine-built, value-balanced offers: they trade surplus depth (never a
cornerstone), pay the market premium a coveted position commands here, and only
send a QB to a QB-needy partner. Prefer these over the raw angles below.
{context.trade_offers}

## League-Specific Mispricing (our exact scoring vs the generic dynasty market)
The trade market prices on generic PPR; we score with bonuses. These are players our
rules value differently than the market does — BUY where we underprice-relative-to-market
is negative (market cheap for us), SELL where the market overpays for a profile our rules
don't reward. This is a real, defensible edge: act on it in trade targeting.
{context.mispricing}

## League Contention Windows (who's buying, who's selling)
Each rival's competitive window and what they want. Target trades at the fit: sell aging
assets to WIN-NOW teams, pry vets from REBUILD teams for picks, don't pitch win-now help
to a RETOOL team hoarding youth.
{context.contention}

## Regression Watch (TD-over-expected — buy-low / sell-high)
Players whose touchdown output ran ahead of or behind their yardage volume last season.
Over-expected scorers are sell-high candidates (TD rate tends to correct down); under-
expected are buy-lows on real, unlucky usage. A lean to time the market, not a verdict.
{context.regression}

## Player Intel (situation research — when a track record stops applying)
Findings from this engine's own studies on why players produce, applied to the roster.
Each flag carries the measured effect behind it, so weigh them by the evidence rather
than by how confident the wording sounds. The three that should actually move a call:
a running back who changed team or play-caller has a usage history that no longer
predicts him — widen his range rather than cutting his projection; a pass catcher with
a new quarterback loses points *per target* while his target count holds, so treat it
as an efficiency event; and attrition risk is about whether a player is startable at
all next season, which is a separate question from how much he declines.
{context.player_intel}

## Trade Candidates (raw positional angles — directional only, not value-balanced)
{context.trade_candidates}

## Handcuffs & Leverage (contingent value)
Which of my starters have an unrostered backup (an injury cliff worth insuring), and
which available backups sit behind rivals' key starters (stashes that create leverage).
{context.handcuffs}

## Wire Early-Warning (snap-share risers, still available)
Players whose offensive snap share is trending up sharply and who are unrostered in this
league — emerging roles to claim before the points show up and the herd bids.
{context.wire_watch}

## Early Claims (engine-flagged, market hasn't noticed)
High-projection free agents with a near-zero Sleeper trending-add count — the engine
likes them and the league hasn't started bidding yet. Backtesting shows this exact
ranking flags real value-add pickups roughly 2x as often as chance before a rival claims
them (`sffm eval earlyclaim`). Reference bids are this league's own median historical
winning bid for the position, priced before any real trend signal exists — a floor to
clear, not a precise estimate. Claim quietly; naming one here starts the clock.
{context.early_claims}

## Best Available (ranked by projected value)
The highest-projected unrostered players this week, league-scored — the pickup ranking the
engine measures best at (arena waiver capture 37-60%). Snap risers above lead the box
score; these price it. A trending count means the herd has already noticed.
{context.best_available}

## Waiver Candidates
{context.waiver_candidates}

## Draft Context
{context.draft_context}

## Prospect Context
{context.prospect_context}

## Lineup Questions
{context.lineup_questions}

## Roster Stadium & Weather Leans (start/sit context)
How my rostered players have historically performed by venue and conditions. Use to
break start/sit ties — fade a cold/wind-averse player outdoors in December, lean into a
dome specialist. Descriptive of past games, not a forecast.
{context.roster_environment}

## Playoff Schedule Outlook (defense-vs-position, weeks 15-17)
Opponent-adjusted schedule softness for my players. Index >1 = soft matchups (good),
<1 = tough. Weight the fantasy-playoff weeks heavily for hold/acquire calls.
{context.schedule_outlook}

## Rival Dossiers (one exploit plan per manager)
Everything you need to plan a winning trade against each rival: their window, roster
holes, positional surplus, pick capital, and top holdings. Produce one dossier per
manager in `owner_dossiers`.
{context.rival_dossiers}

---
## Your Task
Produce ONE GM update — the single source of truth for the whole app this cycle. Cover
every surface above:
1. `narrative`: the GM's weekly column (voice + substance per the schema).
2. `trade_recs`: concrete trades grounded in the positional angles.
3. `waiver_recs`: FAAB moves ($500 budget) with the drop.
4. `draft_recs`: draft calls (if a draft is active or approaching).
5. `prospect_notes`: names worth tracking (one-line verdicts; deep scouting lives elsewhere).
6. `lineup_recs`: start/sit calls (in-season only).
7. `trade_plan`: franchise BUY/SELL/HOLD posture, defended from title equity + window,
   with the sequenced plan.
8. `market_edge`: reconcile mispricing + regression + opponent-adjusted into buy/sell
   theses, resolving where the boards disagree on a player.
9. `waiver_plan`: a disciplined bid plan — rank claims by tier (PRIORITY/SPECULATIVE/DART),
   size FAAB, and name the trending players you deliberately hold off on.
10. `owner_dossiers`: one exploit plan per rival — their holes, and offers framed around
    what they need and will part with, ranked by likelihood to close.

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
        mispricing=_mispricing_section(),
        roster_environment=_environment_section(my_roster_id),
        schedule_outlook=_schedule_outlook_section(my_roster_id),
        title_equity=_title_equity_section(my_roster_id),
        contention=_contention_section(my_roster_id),
        regression=_regression_section(),
        player_intel=_player_intel_section(my_roster_id),
        handcuffs=_handcuff_section(my_roster_id),
        wire_watch=_wire_watch_section(my_roster_id),
        early_claims=_early_claim_section(my_roster_id),
        best_available=_best_available_section(),
        transaction_grades=_transaction_grades_section(my_roster_id),
        rival_dossiers=_rival_dossiers_section(my_roster_id),
        track_record=_track_record_section(),
        data_freshness=_data_freshness_section(),
    )


def _track_record_section() -> str:
    """Graded hit-rate of the GM's own past lineup/waiver calls (calibration feedback)."""
    try:
        from sleeper_ffm.model.rec_scoreboard import build_scoreboard

        board = build_scoreboard()
    except Exception as exc:
        log.warning("master: track record unavailable: %s", exc)
        return "(degraded — recommendation scoreboard unavailable)"

    if not board.recs:
        return "  (no past recommendations posted yet — no track record to calibrate against)"

    overall = f"{board.overall_hit_rate:.0%}" if board.overall_hit_rate is not None else "n/a"
    lines = [
        f"  Overall graded hit-rate: {overall} "
        f"({board.graded_count} graded, {board.pending_count} pending)"
    ]
    for k in board.by_kind:
        rate = f"{k.hit_rate:.0%}" if k.hit_rate is not None else "—"
        lines.append(
            f"    {k.kind}: {rate} hit-rate ({k.correct}/{k.graded} graded, {k.total} total)"
        )
    for w in board.warnings[:2]:
        lines.append(f"  note: {w}")
    return "\n".join(lines)


def _data_freshness_section() -> str:
    """Surface any stale-fallback the loaders recorded so the GM can acknowledge it."""
    try:
        from sleeper_ffm.nflverse.loader import stale_fallbacks

        stale = stale_fallbacks()
    except Exception as exc:
        log.warning("master: data freshness unavailable: %s", exc)
        return "(freshness check unavailable — assume sources may be stale)"

    if not stale:
        return "  (no stale-data fallbacks flagged this cycle)"
    return "\n".join(f"  [STALE] {source}: {detail}" for source, detail in sorted(stale.items()))


def _wire_watch_section(my_roster_id: int, top: int = 8) -> str:
    """Available snap-share risers from the wire early-warning engine."""
    try:
        from sleeper_ffm.model.wire_watch import build_wire_watch

        watch = build_wire_watch(my_roster_id=my_roster_id)
    except Exception as exc:
        log.warning("master: wire watch unavailable: %s", exc)
        return "(degraded — wire watch unavailable)"

    available = [a for a in watch.alerts if a.available][:top]
    if not available:
        note = "; ".join(watch.warnings) or "no risers cleared the bar"
        return f"  (no available risers — {note})"
    return "\n".join(f"  {a.name} ({a.position} {a.team}): {a.note}" for a in available)


def _early_claim_section(my_roster_id: int, top: int = 8) -> str:
    """High-projection free agents the trending board hasn't caught up to yet."""
    try:
        from sleeper_ffm.model.early_claim_watch import build_early_claim_watch

        watch = build_early_claim_watch(my_roster_id=my_roster_id, top_n=top)
    except Exception as exc:
        log.warning("master: early-claim watch unavailable: %s", exc)
        return "(degraded — early-claim watch unavailable)"

    if not watch.claims:
        note = "; ".join(watch.warnings) or "nothing cleared the quiet-market bar this week"
        return f"  (no early claims — {note})"
    lines: list[str] = []
    for c in watch.claims:
        bid = f", ref bid ${c.suggested_bid}" if c.suggested_bid is not None else ""
        drop = f", drop {c.drop_candidate}" if c.drop_candidate else ""
        lines.append(
            f"  {c.name} ({c.position} {c.team}): {c.projected_pts:.1f} proj, "
            f"{c.trending_add_count} adds league-wide{bid}{drop}"
        )
    return "\n".join(lines)


def _fmt_dossier_player(p: dict) -> str:
    return (
        f"{p.get('name', '?')} ({p.get('position', '?')} {p.get('team', '?')}, "
        f"{p.get('dynasty_value', 0):.0f})"
    )


def _dossier_section(roster_id: int) -> str:
    """Render one rival's full dossier (holdings, needs, window, picks) for reasoning.

    Runs inside a degrade guard so a dataclass field drift downgrades one manager's block
    to a placeholder rather than failing the whole briefing.
    """
    try:
        from sleeper_ffm.config import DEFAULT_VALUE_SEASON
        from sleeper_ffm.model.owner_dossier import build_dossier

        d = build_dossier(roster_id, DEFAULT_VALUE_SEASON)
        pos_val = ", ".join(f"{p.position} {p.value:.0f}" for p in d.value_by_position)
        ranks = ", ".join(f"{r.position} #{r.rank}/{r.of} ({r.tier})" for r in d.position_ranks)
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
        log.warning("master: dossier unavailable for roster %s: %s", roster_id, exc)
        return f"(degraded — dossier for roster {roster_id} unavailable)"


def _rival_dossiers_section(my_roster_id: int) -> str:
    """One dossier context block per rival manager, for the master run's owner_dossiers.

    Gives the consolidated master run exactly what the retired standalone ``/ai/dossier``
    prompt had — just for every rival at once. Degrades to a note if the roster list is
    unavailable.
    """
    try:
        from sleeper_ffm.sleeper.client import SleeperClient

        with SleeperClient() as client:
            roster_ids = sorted(int(r.roster_id) for r in client.rosters())
    except Exception as exc:
        log.warning("master: rival dossiers unavailable: %s", exc)
        return "(degraded — rival dossiers unavailable)"

    blocks = [_dossier_section(rid) for rid in roster_ids if rid != my_roster_id]
    return "\n\n".join(blocks) if blocks else "  (no rival rosters found)"


def _best_available_section(top: int = 10) -> str:
    """Highest-projected unrostered players — the projection-ranked free-agent board."""
    try:
        from sleeper_ffm.model.free_agents import build_free_agent_board

        board = build_free_agent_board(top_n=top)
    except Exception as exc:
        log.warning("master: free-agent board unavailable: %s", exc)
        return "(degraded — free-agent board unavailable)"

    if not board.overall:
        note = "; ".join(board.warnings) or "no available players cleared the bar"
        return f"  (no ranked free agents — {note})"
    lines: list[str] = []
    for fa in board.overall:
        inj = f" [{fa.injury_status}]" if fa.injury_status else ""
        trend = f" (herd +{fa.trending_add_count})" if fa.trending_add_count else ""
        lines.append(
            f"  {fa.name} ({fa.position} {fa.team}): {fa.projected_pts:.1f} proj{inj}{trend}"
        )
    return "\n".join(lines)


def _handcuff_section(my_roster_id: int) -> str:
    """Exposed handcuffs on my roster + available leverage stashes."""
    try:
        from sleeper_ffm.model.handcuff import build_handcuff_map

        hc = build_handcuff_map(my_roster_id)
    except Exception as exc:
        log.warning("master: handcuff map unavailable: %s", exc)
        return "(degraded — handcuff map unavailable)"

    lines: list[str] = ["  Exposed starters (backup not on my roster):"]
    lines += [
        f"    {h.starter_name} ({h.position} {h.team}) → backup "
        f"{h.backup_name or 'none'} [{h.backup_owner}]"
        for h in hc.exposed[:8]
    ] or ["    (none — contingent value secured)"]
    lines.append("  Leverage stashes (free-agent backups behind rivals' starters):")
    lines += [
        f"    {s.backup_name} ({s.position} {s.team}) behind {s.starter_name} [{s.starter_owner}]"
        for s in hc.leverage_stashes[:6]
    ] or ["    (none available)"]
    return "\n".join(lines)


def _player_intel_section(my_roster_id: int, top: int = 12) -> str:
    """Research-backed situation flags for rostered players (studies S2-S6)."""
    try:
        from sleeper_ffm.model.context_table import load_context_table
        from sleeper_ffm.model.player_intel import build_roster_intel
        from sleeper_ffm.model.research.archetypes import build as build_archetypes
        from sleeper_ffm.sleeper.client import SleeperClient

        context = load_context_table()
        if context.is_empty():
            return "  (no context table — run `sffm ingest` to build it)"

        with SleeperClient() as client:
            rosters = client.rosters()
        mine = next((r for r in rosters if r.roster_id == my_roster_id), None)
        held = {str(p) for p in (mine.players if mine else [])}
        if not held:
            return "  (roster empty or unavailable — no players to report intel on)"

        try:
            latest = context["season"].max()
            if not isinstance(latest, (int, float)):
                raise ValueError(f"context table has no usable season: {latest!r}")
            archetypes = build_archetypes([int(latest)])
        except Exception as exc:
            log.warning("master: archetypes unavailable, attrition flags omitted: %s", exc)
            archetypes = None

        try:
            from sleeper_ffm.model.research.qb_quality import team_qb_context

            qb_context = team_qb_context(int(latest)) if isinstance(latest, (int, float)) else {}
        except Exception as exc:
            log.warning("master: QB context unavailable (%s)", exc)
            qb_context = {}

        intel = build_roster_intel(
            context, archetypes=archetypes, sleeper_ids=held, qb_context=qb_context
        )
    except Exception as exc:
        log.warning("master: player intel unavailable: %s", exc)
        return "(degraded — player intel unavailable)"

    flagged = [i for i in intel if i.flags]
    if not flagged:
        return "  (no situation flags — no rostered player changed team, coach or quarterback)"

    lines: list[str] = []
    for record in flagged[:top]:
        header = f"  {record.name} ({record.position}"
        if record.team:
            header += f", {record.team}"
        if record.age is not None:
            header += f", age {record.age:.0f}"
        if record.archetype:
            header += f", {record.archetype.replace('_', ' ')}"
        lines.append(header + ")")
        for flag in record.flags:
            lines.append(f"    [{flag.severity}] {flag.headline}")
            lines.append(f"      evidence ({flag.study}): {flag.evidence}")
    if len(flagged) > top:
        lines.append(f"  ... and {len(flagged) - top} more flagged players")
    return "\n".join(lines)


def _regression_section(top: int = 8) -> str:
    """TD-over-expected buy-low / sell-high candidates."""
    try:
        from sleeper_ffm.model.regression import build_regression

        board = build_regression(top=top)
    except Exception as exc:
        log.warning("master: regression unavailable: %s", exc)
        return "(degraded — regression engine unavailable)"

    if not board.sell_high and not board.buy_low:
        note = "; ".join(board.warnings) or "no qualifying players"
        return f"  (no regression signal — {note})"
    lines = ["  SELL-HIGH (rode TD variance up):"]
    lines += [
        f"    {f.name} ({f.position} {f.team}): {f.total_tds:.0f} TDs vs "
        f"{f.expected_tds:.1f} expected (+{f.td_oe:.1f})"
        for f in board.sell_high
    ] or ["    (none)"]
    lines.append("  BUY-LOW (unlucky on real usage):")
    lines += [
        f"    {f.name} ({f.position} {f.team}): {f.total_tds:.0f} TDs vs "
        f"{f.expected_tds:.1f} expected ({f.td_oe:.1f})"
        for f in board.buy_low
    ] or ["    (none)"]
    return "\n".join(lines)


def _contention_section(my_roster_id: int) -> str:
    """League contention windows with buy/sell guidance per roster."""
    try:
        from sleeper_ffm.model.contention import build_contention

        board = build_contention(n_sims=2000)
    except Exception as exc:
        log.warning("master: contention unavailable: %s", exc)
        return "(degraded — contention classifier unavailable)"

    lines: list[str] = []
    for w in board.windows:
        tag = " ← my team" if w.roster_id == my_roster_id else ""
        lines.append(
            f"  roster {w.roster_id} [{w.label}] playoff {w.playoff_odds:.0%}, "
            f"core age {w.core_age:.1f}, youth {w.young_share:.0%}{tag} — "
            f"wants {w.seeking}; should move {w.shedding}"
        )
    return "\n".join(lines) if lines else "(no rosters classified)"


def _title_equity_section(my_roster_id: int) -> str:
    """Per-team playoff/title odds from the Monte-Carlo season simulator."""
    try:
        from sleeper_ffm.model.season_sim import build_season_sim

        sim = build_season_sim(n_sims=2000)
    except Exception as exc:
        log.warning("master: title equity unavailable: %s", exc)
        return "(degraded — season simulation unavailable)"

    caveat = sim.warnings[0] if sim.warnings else ""
    lines = [f"  _{sim.schedule_source} schedule, {sim.n_sims} sims. {caveat}_".rstrip()]
    for rank, t in enumerate(sim.teams, start=1):
        tag = " ← my team" if t.roster_id == my_roster_id else ""
        lines.append(
            f"  {rank}. roster {t.roster_id}: title {t.title_odds:.0%}, "
            f"playoff {t.playoff_odds:.0%}, ~{t.avg_wins:.1f} wins, "
            f"strength {t.strength:.0f}/wk{tag}"
        )
    return "\n".join(lines)


def _my_roster_players(my_roster_id: int) -> dict[str, tuple[str, str, str]]:
    """Return ``{player_id: (name, position, team)}`` for my rostered skill players."""
    from sleeper_ffm.model.valuation import SKILL_POSITIONS
    from sleeper_ffm.sleeper.client import SleeperClient

    with SleeperClient() as c:
        rosters = c.rosters()
        players = c.players()
    mine = next((r for r in rosters if r.roster_id == my_roster_id), None)
    if mine is None:
        return {}
    ids: set[str] = set(mine.players or []) | set(mine.taxi or []) | set(mine.reserve or [])
    out: dict[str, tuple[str, str, str]] = {}
    for pid in ids:
        meta = players.get(pid, {})
        pos = meta.get("position")
        if pos in SKILL_POSITIONS:
            out[pid] = (meta.get("full_name") or pid, pos, meta.get("team") or "FA")
    return out


def _mispricing_section(top: int = 8) -> str:
    """Buy/sell board from the scoring-leverage mispricing engine."""
    try:
        from sleeper_ffm.model.mispricing import build_mispricing, mispricing_summary

        return mispricing_summary(build_mispricing(top=top), limit=top).rstrip()
    except Exception as exc:
        log.warning("master: mispricing unavailable: %s", exc)
        return "(degraded — mispricing engine unavailable)"


def _environment_section(my_roster_id: int) -> str:
    """Stadium/weather leans for my rostered players."""
    try:
        from sleeper_ffm.model.stadium_weather import build_environment_splits

        profiles = build_environment_splits()
        mine = _my_roster_players(my_roster_id)
    except Exception as exc:
        log.warning("master: environment section unavailable: %s", exc)
        return "(degraded — stadium/weather splits unavailable)"

    lines: list[str] = []
    for pid, (name, pos, team) in mine.items():
        prof = profiles.get(pid)
        if prof and prof.flags:
            lines.append(f"  {name} ({pos} {team}): " + "; ".join(prof.flags))
    return "\n".join(lines) if lines else "  (no material stadium/weather leans on the roster)"


def _schedule_outlook_section(my_roster_id: int) -> str:
    """Playoff-weighted DvP schedule softness for my rostered players."""
    try:
        from sleeper_ffm.model.schedule_strength import build_schedule_strength

        ss = build_schedule_strength()
        mine = _my_roster_players(my_roster_id)
    except Exception as exc:
        log.warning("master: schedule outlook unavailable: %s", exc)
        return "(degraded — schedule strength unavailable)"

    if not ss.sos:
        note = "; ".join(ss.warnings) or "no schedule data"
        return f"  (schedule outlook unavailable — {note})"

    sos_map = {(s.team, s.position): s for s in ss.sos}
    elo_map = {e.team: e for e in ss.elo_sos}
    lines: list[str] = []
    for _pid, (name, pos, team) in mine.items():
        s = sos_map.get((team, pos))
        if s and s.playoff_weeks_counted:
            # Opponent team-strength (Elo) is a forward read for the playoff weeks Vegas
            # hasn't priced; DvP is the position-specific defensive read.
            elo = elo_map.get(team)
            elo_note = (
                f", playoff opp-strength {elo.playoff_difficulty:.2f}x"
                if elo and elo.playoff_weeks_counted
                else ""
            )
            lines.append(
                f"  {name} ({pos} {team}): playoff DvP {s.playoff_index:.2f}, "
                f"full-season {s.full_season_index:.2f}{elo_note}"
            )
    lines.sort(key=lambda ln: ln)
    return "\n".join(lines) if lines else "  (no playoff schedule data for rostered players)"


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


def _transaction_grades_section(my_roster_id: int, recent: int = 8) -> str:
    """League GPA standings plus the most recent graded trades and waiver claims."""
    try:
        from sleeper_ffm.model.transaction_grades import build_transaction_grades

        book = build_transaction_grades()
    except Exception as exc:
        log.warning("master: transaction grades unavailable: %s", exc)
        return "(degraded — transaction grades unavailable)"

    if not book.gpa:
        note = "; ".join(book.warnings) or "no gradeable moves found"
        return f"  (no transaction grades — {note})"

    lines = ["  GPA standings:"]
    for g in book.gpa:
        me = " (you)" if g.roster_id == my_roster_id else ""
        lines.append(f"    {g.gpa:.2f} {g.owner_name}{me} — {g.n_moves} graded moves")

    moves: list[tuple[str, int, str]] = []
    for w in book.waiver_grades:
        settle = " SETTLING" if w.settling else ""
        moves.append(
            (
                w.season,
                w.week,
                f"    [{w.grade}{settle}] {w.owner_name}: {w.player_name} (${w.bid}, "
                f"{w.realized_points:.0f} pts, surplus {w.surplus:+.0f})",
            )
        )
    for t in book.trade_grades:
        settle = " SETTLING" if t.settling else ""
        dd = f", dynasty {t.dynasty_delta:+.0f}" if t.dynasty_delta is not None else ""
        moves.append(
            (
                t.season,
                t.week,
                f"    [{t.grade}{settle}] {t.owner_name} vs {t.partner_name}: "
                f"net {t.net_points:+.0f} pts{dd}",
            )
        )
    moves.sort(key=lambda m: (m[0], m[1]), reverse=True)
    lines.append("  Most recent graded moves:")
    lines.extend(line for _season, _week, line in moves[:recent])
    return "\n".join(lines)


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
    # Sleeper reports week 0 out of season and the context coerces that to 1, so
    # naming a week here would assert a Week 1 that has not happened yet.
    league_state = (
        f"Season {ctx.season}, Week {ctx.week} ({ctx.season_type.upper()})."
        if ctx.season_type == "regular"
        else f"Season {ctx.season}, {ctx.season_type.upper()}-SEASON (no games played yet)."
    )
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
    """Live draft board summary + the actual available pool (rookies + free agents).

    The board header describes where my pick falls; the pool is the *groundable* part —
    the incoming rookie class plus unrostered free agents, value-ranked, so a pick can be
    recommended by name instead of a stale generic prospect board.
    """
    try:
        from sleeper_ffm.draft.assistant import sync_board

        board = sync_board()
    except Exception as exc:
        log.info("master: no active draft board (%s)", exc)
        return "(no active draft — off-season or draft complete)"

    if board.is_complete():
        return "(draft complete — no live picks)"

    # Spell out every pick I actually hold. Naming only the next one lets a plan
    # be built around a round whose pick was traded away.
    owned = board.my_pick_numbers
    if owned and len(owned) != board.total_rounds:
        rounds = sorted({(n - 1) // board.total_teams + 1 for n in owned})
        pick_inventory = (
            f" I hold {len(owned)} of {board.total_rounds} picks this draft — overall "
            f"{', '.join(str(n) for n in owned)} (rounds {', '.join(str(r) for r in rounds)}). "
            "The missing rounds were traded away, so do not plan a pick in them."
        )
    elif owned:
        pick_inventory = f" My picks: overall {', '.join(str(n) for n in owned)}."
    else:
        pick_inventory = ""

    pick_no: int | None
    if board.order_confirmed:
        header = (
            f"Live draft: pick {board.current_pick_no}/{board.total_picks} "
            f"(round {board.current_round}), {board.picks_until_my_turn} picks until my turn."
            f"{pick_inventory}"
        )
        pick_no = board.next_my_pick or board.current_pick_no
    elif board.order_projected and board.my_slot is not None:
        header = (
            f"Draft created ({board.total_picks} picks, {board.total_teams} teams). Sleeper has "
            f"NOT yet officially set the draft order, but this league's rookie draft order is a "
            f"verified convention (reverse of the full final standings from the prior completed "
            f"season, {board.projection_source_season}) — under that rule my projected slot is "
            f"{board.my_slot}, with pick {board.next_my_pick} overall "
            f"({board.picks_until_my_turn} picks away).{pick_inventory} Treat this as a strong "
            "projection, not an official Sleeper-confirmed slot — a name recommended as 'the "
            "pick' must account for how many picks happen before this projected turn, since top "
            "names may not survive."
        )
        pick_no = board.next_my_pick
    else:
        header = (
            f"Draft created ({board.total_picks} picks, {board.total_teams} teams) but Sleeper has "
            "NOT yet set/randomized the draft order, and no standings-based projection was "
            "available either — there is no confirmed or projected pick number yet. Do not state a "
            "specific slot or 'picks until my turn' as fact; recommend players generally and note "
            "the order is pending."
        )
        pick_no = None

    # Inject the real, groundable pool: incoming rookies + unrostered free agents, value-ranked.
    # `is_taxi` is set True by the rookie builder and False for unrostered veterans, so it is the
    # authoritative rookie-vs-free-agent tag on each asset.
    try:
        from sleeper_ffm.draft.assistant import build_full_pool
        from sleeper_ffm.sleeper.client import SleeperClient

        with SleeperClient() as c:
            sleeper_players = c.players()
        pool = build_full_pool(board, sleeper_players=sleeper_players)
    except Exception as exc:
        log.warning("master: draft pool build failed (%s)", exc)
        return header + "\n(available-player pool unavailable this cycle — recommend generally)"

    if not pool:
        return header + "\n(no unrostered rookies or free agents surfaced in the pool this cycle)"

    # Draft-capital base rates (study S6). A board ranked only on projected value says
    # which prospect is best without saying how often that kind of prospect works out.
    try:
        from sleeper_ffm.config import CURRENT_LEAGUE_YEAR
        from sleeper_ffm.model.player_intel import rookie_hit_rates

        hit_rates = rookie_hit_rates(int(CURRENT_LEAGUE_YEAR))
    except Exception as exc:
        log.warning("master: rookie hit rates unavailable (%s)", exc)
        hit_rates = {}

    lines = [
        header,
        "",
        "Best available now — incoming rookie class + unrostered free agents, ranked by model "
        "value ([R] = rookie/year-1, [FA] = unrostered veteran).",
    ]
    if hit_rates:
        lines.append(
            "Rookies carry their NFL draft-capital tier and the measured probability of ever "
            "producing a startable season here (study S6, career years 1-3, this league's own "
            "replacement line): tier A = rounds 1-2, 58%; tier B = rounds 3-5, 21%; tier C = "
            "round 6, undrafted or unknown, 3%. Inside tier A this lineup makes running backs "
            "far safer than quarterbacks (88% vs 39%) because it starts three backs plus two "
            "flexes and one quarterback. Weigh a value ranking against these base rates — a "
            "tier-C prospect ranked highly on projection is still a 3% shot."
        )
    # College context for the incoming class. Without it the reasoning is asked to
    # rank rookies on a value number alone, blind to whether a prospect led his
    # offence or was a complementary piece.
    try:
        from sleeper_ffm.cfbd.loader import college_context

        college_by_id = college_context()
    except Exception as exc:
        log.warning("master: college context unavailable (%s)", exc)
        college_by_id = {}

    lines.append("")
    for i, p in enumerate(pool[:24], start=1):
        tag = "R " if p.is_taxi else "FA"
        gone = pick_no is not None and i < pick_no
        marker = "  ← likely gone before my pick" if gone else ""
        prior = ""
        if p.is_taxi:
            info = hit_rates.get(str(p.player_id))
            if info is None:
                prior = " — no draft capital on record (tier C, 3%)"
            else:
                rnd = info["round"]
                where = f"rd {rnd}" if rnd is not None else "undrafted"
                rate = info["rate"]
                rate_txt = f"{rate:.0%}" if isinstance(rate, float) else "n/a"
                prior = f" — {where}, tier {info['tier']} {rate_txt}"
                pos_rate = info.get("position_rate")
                if isinstance(pos_rate, float):
                    prior += f" ({p.position} in this tier: {pos_rate:.0%})"
        college = college_by_id.get(p.player_id) or {}
        college_note = ""
        if college:
            bits = []
            if college.get("college"):
                bits.append(str(college["college"]))
            if college.get("usage_rate"):
                bits.append(f"{college['usage_rate']:.0%} of team plays")
            if college.get("recruiting_rank") is not None:
                bits.append(f"#{college['recruiting_rank']} recruit")
            if bits:
                college_note = " — " + ", ".join(bits)
        lines.append(
            f"  {i:>2}. [{tag}] {p.position:2} {p.name} ({p.team or 'FA'}) — val "
            f"{p.current_fpar:.0f}{prior}{college_note}{marker}"
        )
    if pick_no is not None:
        lines.append(
            f"  Roughly the top {max(pick_no - 1, 0)} come off before my projected pick {pick_no}; "
            "the realistic target is the best value that survives to that range, not the #1."
        )
    return "\n".join(lines)


def _prospect_context() -> str:
    """College standouts for the incoming class, plus the prospect-watch brief.

    This used to be instruction text alone, which asked for prospect verdicts
    while supplying nothing to form them from. The names below are the ones whose
    college role stands out, which is a different question from the value ranking
    in the draft pool — the point is the disagreements between the two.
    """
    brief = (
        "Flag any name worth a full scouting dive in `prospect_notes` with a one-line verdict — "
        "draw from the [R] rookies in the draft pool above and from young stashes already on my "
        "roster (taxi squad, buried-but-talented bench). Deep per-player scouting runs via the "
        "prospect surface; here just surface who deserves that dive and why."
    )

    try:
        from sleeper_ffm.cfbd.loader import college_context

        college = college_context()
    except Exception as exc:
        log.warning("master: prospect college context unavailable (%s)", exc)
        return brief

    # Usage is not comparable across positions — a quarterback touches roughly
    # 60% of his team's plays by definition and a receiver 12%, so one combined
    # ranking is all quarterbacks and says nothing. Rank inside each position.
    by_position: dict[str, list[dict]] = {}
    for c in college.values():
        if c.get("usage_rate"):
            by_position.setdefault(str(c.get("position") or "??"), []).append(c)
    if not by_position:
        return brief

    lines = [
        "Biggest college offensive role by position (share of team plays). Usage is only "
        "comparable within a position. This is a different question from the value ranking "
        "above — where the two disagree is the interesting part:",
    ]
    for position in ("RB", "WR", "TE", "QB"):
        group = sorted(by_position.get(position, []), key=lambda c: c["usage_rate"], reverse=True)[
            :4
        ]
        if not group:
            continue
        lines.append(f"  {position}:")
        for c in group:
            rank = c.get("recruiting_rank")
            pedigree = f", #{rank} recruit" if rank is not None else ", unranked recruit"
            lines.append(
                f"    {c.get('name', 'unknown')} ({c.get('college') or 'unknown'}) — "
                f"{c['usage_rate']:.0%}{pedigree}"
            )
    lines.append("")
    lines.append(brief)
    return "\n".join(lines)
