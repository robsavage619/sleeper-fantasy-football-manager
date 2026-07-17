"""Tier-3 briefing fixtures — hand-built contexts with planted traps.

Each fixture renders through the real, current ``build_master_briefing``
template, so the eval always exercises the prompt wording actually being
tuned rather than a frozen snapshot. The paired ``ExpectSpec`` is scripted
grading material: it never changes what the model reasons about, only what
a passing answer must and must not contain.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sleeper_ffm.prompts.master import BriefingContext, build_master_briefing


@dataclass
class ExpectSpec:
    """Scriptable, planted-fact assertions for one tier-3 fixture."""

    must_mention: list[str] = field(default_factory=list)
    must_not_mention: list[str] = field(default_factory=list)
    allowed_player_names: list[str] = field(default_factory=list)
    faab_bounds: dict[str, tuple[float, float]] = field(default_factory=dict)
    ack_must_contain: list[str] = field(default_factory=list)


@dataclass
class BriefingFixture:
    """A frozen briefing context paired with its scripted expectations."""

    name: str
    context: BriefingContext
    expect: ExpectSpec


def _fixture_hallucinated_partner() -> BriefingFixture:
    context = BriefingContext(
        league_state="Week 9. Ten-team 1QB dynasty. Rosters mostly stable, no bye-week chaos.",
        my_roster=(
            "QB Marcus Vale, RB Devon Cole, RB Trey Sharp, WR Isaiah Boone, "
            "WR Kelvin Ash, TE Andre Vick."
        ),
        saber_summary="Roster consistency is above league median; no red flags.",
        intel_feed=(
            "RUMOR (unconfirmed, treat as noise): Team Osprey has been fielding calls on "
            "their WR2 but nothing is close. No injury news this week."
        ),
        trade_offers=(
            "[HIGH impact | FIT 82 OWNER-HISTORY] send Trey Sharp (~92) to Team Falcon "
            "(roster 7) for Corbin Reyes (~98) — 24/30 roster-fit, +6.2 value margin in "
            "your favor, OPEN approachability, 6 historical trades; land WR need at fair "
            "value (WR is 32% of this league's trades) — the only realistic offer this cycle."
        ),
        trade_candidates=(
            "RB depth is thin league-wide (scarce, high acquire cost). WR2/WR3 is the "
            "most-traded tier in this league by volume (32% of trades) — high demand, "
            "not abundant supply."
        ),
        waiver_candidates=(
            "Free agent WR Jamal Otis: trending add, 40% owned. Fair value for this add is "
            "$12-$18 FAAB given current league bid history."
        ),
        draft_context="No active rookie/offseason draft this week.",
        prospect_context="No new college box scores to review this week.",
        lineup_questions="No lineup decisions — off week for my roster's bye.",
    )
    expect = ExpectSpec(
        must_mention=["Team Falcon"],
        must_not_mention=["Team Osprey"],
        allowed_player_names=[
            "Marcus Vale",
            "Devon Cole",
            "Trey Sharp",
            "Isaiah Boone",
            "Kelvin Ash",
            "Andre Vick",
            "Corbin Reyes",
            "Jamal Otis",
        ],
        faab_bounds={"Jamal Otis": (12, 18)},
    )
    return BriefingFixture("trap_hallucinated_partner", context, expect)


def _fixture_stale_data() -> BriefingFixture:
    context = BriefingContext(
        league_state=(
            "Week 15. Fantasy playoffs underway. NOTE: weekly nflverse data is cached "
            "through 2025 week 14 only — week 15 stats are not yet available."
        ),
        my_roster="QB Reid Colton, RB Marquis Dey, WR Antoine Vela, TE Sammy Okafor.",
        saber_summary="(degraded — insufficient current-week data)",
        intel_feed="No new injury designations reported this week.",
        trade_offers="(no realistic offers cleared the bar this cycle)",
        trade_candidates="(no positional angles surfaced this cycle)",
        waiver_candidates="(no trending adds cleared the bar this cycle)",
        draft_context="No active draft.",
        prospect_context="No new prospect data.",
        lineup_questions="Start/sit call needed for Marquis Dey vs. Antoine Vela at FLEX.",
    )
    expect = ExpectSpec(
        allowed_player_names=["Reid Colton", "Marquis Dey", "Antoine Vela", "Sammy Okafor"],
        ack_must_contain=["week 14"],
    )
    return BriefingFixture("trap_stale_data", context, expect)


def _fixture_closed_universe() -> BriefingFixture:
    context = BriefingContext(
        league_state="Week 5. Early season, no major injuries.",
        my_roster="QB Dallin Chase, RB Corey Wynn, WR Malik Frost, TE Gio Salter.",
        saber_summary="No red flags.",
        intel_feed="No injury or depth-chart changes this week.",
        trade_offers="(no realistic offers cleared the bar this cycle)",
        trade_candidates="RB is the league's deepest position right now.",
        waiver_candidates="Free agent RB Terrence Voss: trending add, thin signal.",
        draft_context="No active draft.",
        prospect_context="No new prospect data.",
        lineup_questions="No lineup decisions this week.",
    )
    expect = ExpectSpec(
        allowed_player_names=[
            "Dallin Chase",
            "Corey Wynn",
            "Malik Frost",
            "Gio Salter",
            "Terrence Voss",
        ],
    )
    return BriefingFixture("trap_closed_universe", context, expect)


def _fixture_timeline_mismatched_trade() -> BriefingFixture:
    """A trade that maths (positive margin, decent fit) but fights the team's own timeline.

    Tier 1 and the other tier-3 fixtures check whether a recommendation is
    internally consistent and grounded — they do not check whether a
    mathematically clean trade is actually *good dynasty strategy*. This
    fixture plants a trade where a rebuilding team (per its own Title Equity
    and Contention Window sections, given in the SAME briefing) would send
    away a future asset (a 1st-round pick + a young ascending WR) for
    short-term veteran production. The raw acceptance-model math is positive
    for the sender, but the move contradicts the explicit rebuild signal a
    real analyst should weigh against it. There is no scriptable check for
    this — it requires an independent dynasty-strategy critique (see the
    engine-eval skill's Tier 3 procedure).
    """
    context = BriefingContext(
        league_state="Week 6. Ten-team 1QB dynasty. No major roster shakeups this week.",
        my_roster=(
            "QB Grant Delacroix, RB Foster Bramwell, WR Deshaun Okoye (age 23, ascending), "
            "WR Milo Castellan, TE Preston Vail."
        ),
        saber_summary="No red flags on process; roster is bottom-third by weekly scoring.",
        intel_feed="No new injury or depth-chart designations this week.",
        trade_offers=(
            "[MED impact | FIT 71 LIMITED-HISTORY] send 2027 1st-round pick (~180) + "
            "Deshaun Okoye (~110) to Team Harrow (roster 4) for Roman Ostrander (~295) — "
            "24/26 roster-fit, +5 value margin in your favor, OPEN approachability, 2 "
            "historical trades; the highest-FIT realistic offer this cycle."
        ),
        trade_candidates="RB is scarce league-wide; proven weekly-starter RBs command a premium.",
        waiver_candidates="(no trending adds cleared the bar this cycle)",
        draft_context="No active rookie/offseason draft this week.",
        prospect_context="No new college box scores to review this week.",
        lineup_questions="No lineup decisions this week.",
        title_equity=(
            "Title odds: 3% (9th of 10 teams by playoff odds). Youth share of total roster "
            "value is 18%, well below league average; value is concentrated in aging "
            "production. Low title equity plus an aging core is a REBUILD signal: the "
            "correct posture is shedding short-term production for picks and ascending "
            "youth, not the reverse."
        ),
        contention=(
            "This roster classifies REBUILD (bottom-third title odds, aging value "
            "distribution). Should be a net seller of veteran production this cycle, "
            "prioritizing picks and ascending youth in return."
        ),
    )
    expect = ExpectSpec(
        allowed_player_names=[
            "Grant Delacroix",
            "Foster Bramwell",
            "Deshaun Okoye",
            "Milo Castellan",
            "Preston Vail",
            "Roman Ostrander",
        ],
    )
    return BriefingFixture("trap_timeline_mismatched_trade", context, expect)


def _fixture_waiver_roster_need_mismatch() -> BriefingFixture:
    """A waiver call where the highest raw priority score isn't the right add.

    The roster is four-deep at WR and has no rostered TE at all — a real
    positional hole. The waiver candidates list ranks a 5th WR above the one
    available TE purely on trending add-priority score. A real analyst
    reconciles priority score against actual roster construction; a response
    that just chases the higher number is exhibiting the same "math checks
    out, team-building doesn't" failure as the timeline-mismatched trade.
    """
    context = BriefingContext(
        league_state="Week 8. Ten-team 1QB dynasty. No bye-week complications this week.",
        my_roster=(
            "QB Silas Renner, RB Andre Kowalski, WR Trevon Ashby, WR Julian Ferro, "
            "WR Dominic Alvarez, WR Cassius Bell. No rostered tight end."
        ),
        saber_summary="No red flags on process.",
        intel_feed="No new injury or depth-chart designations this week.",
        trade_offers="(no realistic offers cleared the bar this cycle)",
        trade_candidates="(no positional angles surfaced this cycle)",
        waiver_candidates=(
            "Trending waiver candidates this cycle, ranked by add-priority score:\n"
            "  1. Bryce Kellerman (WR): add_priority 82, 55% owned, fair value $28-$35 FAAB.\n"
            "  2. Owen Marchetti (TE): add_priority 61, 12% owned, fair value $5-$8 FAAB."
        ),
        draft_context="No active rookie/offseason draft this week.",
        prospect_context="No new college box scores to review this week.",
        lineup_questions="No lineup decisions this week.",
    )
    expect = ExpectSpec(
        allowed_player_names=[
            "Silas Renner",
            "Andre Kowalski",
            "Trevon Ashby",
            "Julian Ferro",
            "Dominic Alvarez",
            "Cassius Bell",
            "Bryce Kellerman",
            "Owen Marchetti",
        ],
    )
    return BriefingFixture("trap_waiver_roster_need_mismatch", context, expect)


def _fixture_startsit_game_script_risk() -> BriefingFixture:
    """A start/sit call where the higher season average isn't the right start.

    Reyes projects higher on raw season average, but his team is a 16.5-point
    road underdog with a stated history of second-half touch-share collapse
    in blowouts; Vance's team projects a competitive, pass-heavy script. A
    response that defaults to "start whoever averages more" without weighing
    the stated game-script risk is missing the same class of judgment gap as
    the trade and waiver traps, applied to lineup decisions.
    """
    context = BriefingContext(
        league_state="Week 11. Ten-team 1QB dynasty. In-season, all rosters active.",
        my_roster=(
            "QB Ezra Wolcott, RB Tomas Reyes, RB Bennett Okafor, WR Silas Vance, "
            "TE Cormac Doyle."
        ),
        saber_summary="No red flags on process.",
        intel_feed="No new injury or depth-chart designations this week.",
        trade_offers="(no realistic offers cleared the bar this cycle)",
        trade_candidates="(no positional angles surfaced this cycle)",
        waiver_candidates="(no trending adds cleared the bar this cycle)",
        draft_context="No active rookie/offseason draft this week.",
        prospect_context="No new college box scores to review this week.",
        lineup_questions=(
            "Start/sit call needed for Tomas Reyes (RB) vs. Silas Vance (WR) at FLEX. "
            "Season averages: Reyes 14.2 pts/game, Vance 11.8 pts/game — Reyes projects "
            "higher on raw scoring average. Context: Reyes's team is a 16.5-point road "
            "underdog this week per the Vegas line; in games with a spread this lopsided, "
            "this offense's backfield has seen touch share collapse in the second half as "
            "they abandon the run to chase points. Vance's team is favored by 2.5 and "
            "projects a competitive, pass-heavy script all game."
        ),
    )
    expect = ExpectSpec(
        allowed_player_names=[
            "Ezra Wolcott",
            "Tomas Reyes",
            "Bennett Okafor",
            "Silas Vance",
            "Cormac Doyle",
        ],
    )
    return BriefingFixture("trap_startsit_game_script_risk", context, expect)


FIXTURES: dict[str, BriefingFixture] = {
    fixture.name: fixture
    for fixture in (
        _fixture_hallucinated_partner(),
        _fixture_stale_data(),
        _fixture_closed_universe(),
        _fixture_timeline_mismatched_trade(),
        _fixture_waiver_roster_need_mismatch(),
        _fixture_startsit_game_script_risk(),
    )
}


def render_briefing(fixture_name: str, generated_at: str = "2026-01-01T00:00:00+00:00") -> str:
    """Render the current production prompt template against a frozen fixture.

    Args:
        fixture_name: A key in ``FIXTURES``.
        generated_at: Timestamp stamped into the rendered briefing.

    Returns:
        The full briefing prompt text, as ``GET /ai/briefing`` would return it.

    Raises:
        ValueError: If ``fixture_name`` is not a known fixture.
    """
    fixture = FIXTURES.get(fixture_name)
    if fixture is None:
        raise ValueError(f"unknown tier-3 fixture: {fixture_name}")
    return build_master_briefing(fixture.context, generated_at)
