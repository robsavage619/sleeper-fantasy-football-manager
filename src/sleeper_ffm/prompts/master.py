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
    "waiver_recs": (
        "array of objects — each {player, faab_bid, drop, rationale}; "
        "faab_bid is a JSON number of dollars (e.g. 12), never a string or a $-prefixed value"
    ),
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
    # League-specific edge sections (default "" so older callers/tests stay valid).
    mispricing: str = ""
    roster_environment: str = ""
    schedule_outlook: str = ""
    title_equity: str = ""
    contention: str = ""
    regression: str = ""
    handcuffs: str = ""
    wire_watch: str = ""
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
        mispricing=_mispricing_section(),
        roster_environment=_environment_section(my_roster_id),
        schedule_outlook=_schedule_outlook_section(my_roster_id),
        title_equity=_title_equity_section(my_roster_id),
        contention=_contention_section(my_roster_id),
        regression=_regression_section(),
        handcuffs=_handcuff_section(my_roster_id),
        wire_watch=_wire_watch_section(my_roster_id),
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
    lines: list[str] = []
    for _pid, (name, pos, team) in mine.items():
        s = sos_map.get((team, pos))
        if s and s.playoff_weeks_counted:
            lines.append(
                f"  {name} ({pos} {team}): playoff SoS {s.playoff_index:.2f}, "
                f"full-season {s.full_season_index:.2f}"
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

    pick_no: int | None
    if board.order_confirmed:
        header = (
            f"Live draft: pick {board.current_pick_no}/{board.total_picks} "
            f"(round {board.current_round}), {board.picks_until_my_turn} picks until my turn."
        )
        pick_no = board.next_my_pick or board.current_pick_no
    elif board.order_projected and board.my_slot is not None:
        header = (
            f"Draft created ({board.total_picks} picks, {board.total_teams} teams). Sleeper has "
            f"NOT yet officially set the draft order, but this league's rookie draft order is a "
            f"verified convention (reverse of the full final standings from the prior completed "
            f"season, {board.projection_source_season}) — under that rule my projected slot is "
            f"{board.my_slot}, with pick {board.next_my_pick} overall "
            f"({board.picks_until_my_turn} picks away). Treat this as a strong projection, not an "
            "official Sleeper-confirmed slot — a name recommended as 'the pick' must account for "
            "how many picks happen before this projected turn, since top names may not survive."
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

    lines = [
        header,
        "",
        "Best available now — incoming rookie class + unrostered free agents, ranked by model "
        "value ([R] = rookie/year-1, [FA] = unrostered veteran):",
    ]
    for i, p in enumerate(pool[:24], start=1):
        tag = "R " if p.is_taxi else "FA"
        gone = pick_no is not None and i < pick_no
        marker = "  ← likely gone before my pick" if gone else ""
        lines.append(
            f"  {i:>2}. [{tag}] {p.position:2} {p.name} ({p.team or 'FA'}) — val "
            f"{p.current_fpar:.0f}{marker}"
        )
    if pick_no is not None:
        lines.append(
            f"  Roughly the top {max(pick_no - 1, 0)} come off before my projected pick {pick_no}; "
            "the realistic target is the best value that survives to that range, not the #1."
        )
    return "\n".join(lines)


def _prospect_context() -> str:
    """Short prospect-watch pointer (deep dives run per-prospect via /prospects)."""
    return (
        "Flag any name worth a full scouting dive in `prospect_notes` with a one-line verdict — "
        "draw from the [R] rookies in the draft pool above and from young stashes already on my "
        "roster (taxi squad, buried-but-talented bench). Deep per-player scouting runs via the "
        "prospect surface; here just surface who deserves that dive and why."
    )
