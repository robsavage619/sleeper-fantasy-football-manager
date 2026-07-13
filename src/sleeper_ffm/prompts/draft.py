"""Draft decision prompt builder.

Assembles a structured prompt for Claude Code to reason over a draft pick decision.
Output goes directly to Claude Code (chat or ``claude -p``); Claude posts the
finding back via ``sffm finding post``.

Context packaged:
  - Current pick number, round, roster construction state
  - Available players (sorted by our dynasty value, filtered by position need)
  - League scoring rules summary (so Claude reasons in this league's currency)
  - Pick inventory (what picks each team holds — positional-run detection context)
  - Vault notes if available (dynasty methodology priors)

The prompt is DETERMINISTIC: same inputs → same prompt. Claude Code is the
non-deterministic reasoning layer; this module is fully testable.
"""

from __future__ import annotations

from sleeper_ffm.model.dynasty import PickAsset, PlayerAsset, RosterAssets


def build_draft_prompt(
    *,
    pick_number: int,
    round_number: int,
    picks_remaining_in_round: int,
    my_roster: RosterAssets,
    available_players: list[PlayerAsset],
    all_picks: dict[int, list[PickAsset]],  # roster_id → picks held
    scoring_summary: str,
    league_name: str = "The League",
    top_n: int = 20,
    vault_notes: str = "",
) -> str:
    """Build a draft decision prompt for Claude Code.

    Args:
        pick_number: Overall pick number in the draft.
        round_number: Current round (1-4).
        picks_remaining_in_round: How many picks until round ends.
        my_roster: Current state of my roster including already-drafted players.
        available_players: Undrafted players sorted by dynasty value descending.
        all_picks: Map of roster_id → list of held picks (for run detection).
        scoring_summary: One-paragraph description of this league's scoring rules.
        league_name: Human-readable league name.
        top_n: How many available players to include in the prompt.
        vault_notes: Relevant vault research passages (optional).

    Returns:
        A structured prompt string ready for Claude Code.
    """
    roster_lines = _format_roster(my_roster)
    board_lines = _format_board(available_players[:top_n])
    picks_lines = _format_picks(all_picks)

    vault_section = ""
    if vault_notes:
        vault_section = f"\n## Vault Research Notes\n{vault_notes}\n"

    return f"""# Draft Decision — Pick {pick_number} (Round {round_number})

## League
{league_name} · {scoring_summary}

## My Roster (dynasty value, age-curve adjusted)
{roster_lines}

## Current Pick Context
- Overall pick: {pick_number}
- Round: {round_number}
- Picks until round ends: {picks_remaining_in_round}

## Available Players (top {top_n} by dynasty value)
{board_lines}

## Pick Inventory Summary
{picks_lines}
{vault_section}
## Your Task
1. Identify the best available player for my roster on a **dynasty** basis (not redraft).
   Weight: long-term value, age curve, positional scarcity, roster construction.
2. Flag any positional runs forming that should change my priority.
3. Name 1-2 alternative picks if my top choice is gone before I pick.
4. If best player available dramatically upgrades a roster need, call it out explicitly.

Respond with:
- **Pick**: player name + position + age + why
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
        lines.append(
            f"  {p.name} ({p.position}, {p.age:.0f}y) — "
            f"FPAR {p.current_fpar:.0f}{taxi}"
        )
    return "\n".join(lines)


def _format_board(players: list[PlayerAsset]) -> str:
    if not players:
        return "  (no players available)"
    lines = []
    for i, p in enumerate(players, 1):
        lines.append(
            f"  {i:2}. {p.name:24s} {p.position:3s}  age {p.age:.0f}"
            f"  FPAR {p.current_fpar:5.1f}"
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
