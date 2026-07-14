"""Draft decision prompt builder.

Assembles a structured prompt for Claude Code to reason over a draft pick decision.
Output goes directly to Claude Code (chat or ``claude -p``); Claude posts the
finding back via ``sffm finding post``.

Context packaged:
  - Current pick number, round, roster construction state
  - Available players (sorted by dynasty value, with steal/reach/survival signals)
  - League scoring rules summary
  - Pick inventory (what picks each team holds — positional-run context)
  - Vault notes if available

The prompt is DETERMINISTIC: same inputs → same prompt. Claude Code is the
non-deterministic reasoning layer; this module is fully testable.
"""

from __future__ import annotations

from sleeper_ffm.model.dynasty import PickAsset, PlayerAsset, RosterAssets, value_player

# Dynasty value tier thresholds.
_TIERS: list[tuple[float, str]] = [
    (350.0, "T1"),  # franchise cornerstone
    (200.0, "T2"),  # starter-quality
    (100.0, "T3"),  # developmental
    (50.0, "T4"),  # depth/flier
    (0.0, "T5"),  # lottery
]


def _tier_label(dynasty_value: float) -> str:
    for threshold, label in _TIERS:
        if dynasty_value >= threshold:
            return label
    return "T5"


def _divergence_label(
    player: PlayerAsset,
    market_values: dict[str, float],
    scale: float,
) -> str:
    """Return a steal/reach/hold signal vs FantasyCalc consensus.

    Compares the age-adjusted dynasty value (model) against the market price on
    the same dynasty-value scale, so old producers are not systematically flagged
    STEAL and young ascenders REACH.

    Positive diff = model rates player higher than market -> STEAL opportunity.
    Negative diff = market rates player higher than model -> REACH risk.
    """
    fc_raw = market_values.get(player.player_id)
    if fc_raw is None or scale <= 0:
        return ""
    market_dv = fc_raw * scale
    if market_dv <= 0:
        return ""
    diff_pct = (value_player(player) - market_dv) / market_dv * 100
    if diff_pct > 20:
        return "★STEAL"  # model rates dynasty value >20% above market
    if diff_pct < -25:
        return "⚠REACH"  # market rates player >25% above model
    return ""


def _survival_signal(rank: int, picks_until: int | None) -> str:
    """Estimate whether a player at this board rank will survive to our next pick."""
    if picks_until is None:
        return ""  # turn position unknown — can't estimate survival odds
    if picks_until == 0:
        return ""  # we're on the clock
    if rank <= picks_until:
        return "GONE?"
    if rank <= picks_until * 1.6:
        return "RISKY"
    return ""


def build_draft_prompt(
    *,
    pick_number: int,
    round_number: int,
    picks_remaining_in_round: int,
    picks_until_my_turn: int | None = 0,
    my_roster: RosterAssets,
    available_players: list[PlayerAsset],
    all_picks: dict[int, list[PickAsset]],
    scoring_summary: str,
    league_name: str = "The League",
    top_n: int = 20,
    vault_notes: str = "",
    market_values: dict[str, float] | None = None,
) -> str:
    """Build a draft decision prompt for Claude Code.

    Args:
        pick_number: Overall pick number in the draft.
        round_number: Current round (1-4).
        picks_remaining_in_round: How many picks until round ends.
        picks_until_my_turn: Picks between now and my next selection (for survival), or
            None if Sleeper hasn't set/randomized the draft order yet.
        my_roster: Current state of my roster including already-drafted players.
        available_players: Undrafted players sorted by dynasty value descending.
        all_picks: Map of roster_id → list of held picks (for run detection).
        scoring_summary: One-paragraph description of this league's scoring rules.
        league_name: Human-readable league name.
        top_n: How many available players to include in the prompt.
        vault_notes: Relevant vault research passages (optional).
        market_values: {sleeper_id: fc_value} for steal/reach signals.

    Returns:
        A structured prompt string ready for Claude Code.
    """
    market_values = market_values or {}
    roster_lines = _format_roster(my_roster)
    board_lines = _format_board(available_players[:top_n], picks_until_my_turn, market_values)
    picks_lines = _format_picks(all_picks)

    vault_section = ""
    if vault_notes:
        vault_section = f"\n## Vault Research Notes\n{vault_notes}\n"

    clock_label = (
        "DRAFT ORDER NOT YET SET — turn position unknown"
        if picks_until_my_turn is None
        else "ON THE CLOCK"
        if picks_until_my_turn == 0
        else f"{picks_until_my_turn} picks away"
    )

    return f"""# Draft Decision — Pick {pick_number} (Round {round_number})

## League
{league_name} · {scoring_summary}

## My Roster (dynasty value, age-curve adjusted)
{roster_lines}

## Current Pick Context
- Overall pick: {pick_number}
- Round: {round_number}
- Picks until round ends: {picks_remaining_in_round}
- My next pick: {clock_label}

## Available Players (top {top_n} by dynasty value)
Legend: T1-T5 tier | STEAL = market underprices | REACH = model overprices | GONE?/RISKY = survival
{board_lines}

## Pick Inventory Summary (future picks by team)
{picks_lines}
{vault_section}
## Your Task
1. Identify the best available player for my roster on a **dynasty** basis (not redraft).
   Weight: long-term value, age curve, positional scarcity, roster construction.
2. Call out any STEAL(★) opportunities — players the market consensus undervalues.
3. Flag REACH(⚠) picks so I don't overpay for consensus darlings.
4. Flag any positional runs forming (GONE?/RISKY rows) that should change my priority.
5. Name 1-2 alternative picks if my top choice is gone before I pick.

Respond with:
- **Pick**: player name + position + age + tier + why
- **Alternatives**: 1-2 named alternatives with brief rationale
- **Roster note**: one sentence on how this pick fits the roster construction arc
- **Run alert** (only if relevant): which position is being drafted fast and what that means

Post your finding via: ``sffm finding post --kind draft --body '<json>'``
where the JSON has keys: ``pick``, ``alternatives``, ``roster_note``, ``run_alert`` (nullable).
"""


def _format_roster(roster: RosterAssets) -> str:
    if not roster.players:
        return "  (empty — first pick)"
    lines = []
    for p in sorted(roster.players, key=lambda x: x.position):
        taxi = " [taxi]" if p.is_taxi else ""
        dv = value_player(p)
        lines.append(
            f"  {p.name} ({p.position}, {p.age:.0f}y) - FPAR {p.current_fpar:.0f} DV {dv:.0f}{taxi}"
        )
    return "\n".join(lines)


def _format_board(
    players: list[PlayerAsset],
    picks_until: int | None,
    market_values: dict[str, float],
) -> str:
    if not players:
        return "  (no players available)"

    from sleeper_ffm.market.blend import FC_TO_DYNASTY_SCALE

    lines = []
    for i, p in enumerate(players, 1):
        dv = value_player(p)
        tier = _tier_label(dv)
        steal = _divergence_label(p, market_values, FC_TO_DYNASTY_SCALE)
        surv = _survival_signal(i, picks_until)
        flags = " ".join(f for f in (steal, surv) if f)
        flag_str = f"  {flags}" if flags else ""
        lines.append(
            f"  {i:2}. [{tier}] {p.name:24s} {p.position:3s}  age {p.age:.0f}"
            f"  FPAR {p.current_fpar:5.1f}  DV {dv:5.0f}{flag_str}"
        )
    return "\n".join(lines)


def _format_picks(all_picks: dict[int, list[PickAsset]]) -> str:
    if not all_picks:
        return "  (no pick data)"
    lines = []
    for roster_id, picks in sorted(all_picks.items()):
        if picks:
            sorted_picks = sorted(picks, key=lambda x: (x.season, x.round))
            pick_strs = [f"{p.season} R{p.round}" for p in sorted_picks]
            lines.append(f"  Roster {roster_id}: {', '.join(pick_strs)}")
    return "\n".join(lines) if lines else "  (all teams hold only their own picks)"
