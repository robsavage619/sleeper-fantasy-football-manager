"""The GM's Weekly Address — a personality-rich 'State of the Franchise' column.

Everything else in the app is decision support; this is the one surface that's meant to
be *read for pleasure*. It reuses the master briefing's assembled facts but asks for a
different artifact: a swaggering, opinionated weekly column in the war-room analyst voice
— receipts included, one bold call made, no hedging.

Pure/testable split mirrors ``prompts.master``: :func:`build_gm_address` renders a prompt
from a :class:`~sleeper_ffm.prompts.master.BriefingContext` and a timestamp with no I/O;
:func:`gather_gm_address` is the live glue.
"""

from __future__ import annotations

from sleeper_ffm.config import MY_ROSTER_ID
from sleeper_ffm.prompts.master import BriefingContext, gather_briefing_context


def build_gm_address(context: BriefingContext, generated_at: str) -> str:
    """Render the weekly-address prompt from briefing context. Pure and deterministic."""
    return f"""# The GM's Weekly Address
Issued: {generated_at}

You are the franchise's General Manager, writing this week's column for the league.
Voice: the 20-year national-analyst war-room voice — opinionated, numbers-literate but
never numbers-drowned, blunt about risk, allergic to unearned hedging. This is a COLUMN,
not a JSON document: write it to be read.

Ground every claim in the facts below. Do not invent players, numbers, or trades.

## Where we stand
{context.league_state}

## Title equity
{context.title_equity}

## The roster
{context.my_roster}

## League contention windows
{context.contention}

## The edges I'm playing
Mispricing:
{context.mispricing}

Regression watch:
{context.regression}

## Real-world intel
{context.intel_feed}

---
## Write the address
Deliver ~4-6 tight paragraphs:
1. **State of the franchise** — contend, retool, or rebuild, and why (cite title equity).
2. **The market read** — one buy-low and one sell-high I'm acting on, with the reasoning.
3. **The bold call** — one confident, specific prediction or move for the week/cycle.
4. **The watch list** — a sentence on the risk I'm monitoring (injury, regression, window).

Make ONE clear call per section. No "on the other hand." Sign off in character.
Post via `sffm finding gm_address --body '<json>'` with keys: `column` (the full text) and
`headline` (a punchy one-liner).
"""


def gather_gm_address(my_roster_id: int = MY_ROSTER_ID, generated_at: str = "") -> str:
    """Assemble live briefing context and render the weekly-address prompt.

    Args:
        my_roster_id: Roster to write the address for.
        generated_at: ISO-8601 timestamp to stamp (caller supplies; keeps this testable).
    """
    context = gather_briefing_context(my_roster_id)
    return build_gm_address(context, generated_at)
