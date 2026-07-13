"""Trade evaluation prompt builder.

Assembles a structured prompt for Claude Code to evaluate a dynasty trade offer.
Like the draft prompt, this is DETERMINISTIC: same inputs → same prompt.

Context packaged:
  - Dynasty values for all players on both sides (GIVE + GET)
  - Pick valuations with round + future-year decay
  - Net dynasty value differential
  - Rob's roster context (position surplus/need)
  - Explicit verdict ask: ACCEPT / DECLINE / COUNTER
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

from sleeper_ffm.config import DEFAULT_VALUE_SEASON
from sleeper_ffm.model.dynasty import PlayerAsset, value_player

log = logging.getLogger(__name__)

_CURRENT_YEAR: int = datetime.date.today().year

# Trade-specific pick valuations (distinct from value_pick in dynasty.py).
# Calibrated to trade context: round 1 ≈ a solid WR2, round 4 ≈ a flier.
_ROUND_BASE_VALUE: dict[int, float] = {
    1: 80.0,
    2: 50.0,
    3: 25.0,
    4: 10.0,
}
_FUTURE_YEAR_DECAY: float = 0.85


@dataclass
class _ParsedPick:
    season: int
    round: int
    slot: int


def _parse_pick_id(pick_id: str) -> _ParsedPick:
    """Parse "2026_2_6" → _ParsedPick(season=2026, round=2, slot=6)."""
    parts = pick_id.split("_")
    if len(parts) != 3:
        raise ValueError(f"expected YEAR_ROUND_SLOT, got {pick_id!r}")
    return _ParsedPick(season=int(parts[0]), round=int(parts[1]), slot=int(parts[2]))


def value_trade_pick(pick_id: str) -> float:
    """Value a pick using trade-specific round values with future-year decay.

    Rounds: 1->80, 2->50, 3->25, 4->10. Each year in the future: x0.85.

    Args:
        pick_id: "YEAR_ROUND_SLOT" format, e.g. "2026_2_6".

    Returns:
        Dynasty value float; 0.0 on parse failure.
    """
    try:
        p = _parse_pick_id(pick_id)
    except (ValueError, IndexError):
        log.warning("could not parse pick_id %r, defaulting to 0", pick_id)
        return 0.0
    base = _ROUND_BASE_VALUE.get(p.round, 5.0)
    years_ahead = max(0, p.season - _CURRENT_YEAR)
    return round(base * (_FUTURE_YEAR_DECAY**years_ahead), 2)


def _pick_label(pick_id: str) -> str:
    """Format "2026_2_6" → "2026 Round 2 (slot 6)"."""
    try:
        p = _parse_pick_id(pick_id)
        return f"{p.season} Round {p.round} (slot {p.slot})"
    except (ValueError, IndexError):
        return pick_id


def _side_label(player_ids: list[str], pick_ids: list[str]) -> str:
    parts = list(player_ids) + [_pick_label(p) for p in pick_ids]
    return ", ".join(parts) if parts else "(nothing)"


def _position_delta(give: list[str], get: list[str]) -> str:
    if not give and not get:
        return "picks only — no positional shift"
    give_c: dict[str, int] = {}
    get_c: dict[str, int] = {}
    for pos in give:
        give_c[pos] = give_c.get(pos, 0) + 1
    for pos in get:
        get_c[pos] = get_c.get(pos, 0) + 1
    all_pos = sorted(set(give) | set(get))
    parts = []
    for pos in all_pos:
        diff = get_c.get(pos, 0) - give_c.get(pos, 0)
        if diff > 0:
            parts.append(f"+{diff} {pos}")
        elif diff < 0:
            parts.append(f"{diff} {pos}")
    return ", ".join(parts) if parts else "even swap by position"


def _format_side(
    players: list[PlayerAsset | None],
    pick_ids: list[str],
) -> str:
    lines: list[str] = []
    for p in players:
        if p:
            dv = value_player(p)
            lines.append(
                f"  {p.name:24s} {p.position:3s}  age {p.age:.0f}"
                f"  FPAR {p.current_fpar:5.1f}  dynasty {dv:.1f}"
            )
        else:
            lines.append("  [unknown player — not in asset database]")
    for pid in pick_ids:
        val = value_trade_pick(pid)
        lines.append(f"  {_pick_label(pid):32s}  dynasty {val:.1f}")
    return "\n".join(lines) if lines else "  (empty)"


def build_trade_prompt(
    give_player_ids: list[str],
    get_player_ids: list[str],
    give_pick_ids: list[str],
    get_pick_ids: list[str],
    seasons: list[int] | None = None,
    vault_notes: str = "",
) -> str:
    """Build a Claude Code prompt for evaluating a trade offer.

    Loads live player data from nflverse + Sleeper, computes dynasty values for
    all players on both sides, and assembles a structured reasoning prompt.

    Args:
        give_player_ids: Sleeper player IDs Rob is giving away.
        get_player_ids: Sleeper player IDs Rob is receiving.
        give_pick_ids: Pick IDs Rob gives (e.g. ["2026_2_6"]).
        get_pick_ids: Pick IDs Rob receives.
        seasons: nflverse seasons for FPAR computation (default: latest completed NFL season).
        vault_notes: Optional vault research to inject.

    Returns:
        Structured prompt string ready for Claude Code.
    """
    from sleeper_ffm.model.valuation import build_player_assets

    seasons = seasons or [DEFAULT_VALUE_SEASON]

    all_ids = set(give_player_ids) | set(get_player_ids)
    if all_ids:
        log.info("loading player assets for trade prompt (%d IDs)", len(all_ids))
        assets = build_player_assets(seasons=seasons)
        asset_map = {p.player_id: p for p in assets}
    else:
        asset_map = {}

    give_players: list[PlayerAsset | None] = [asset_map.get(pid) for pid in give_player_ids]
    get_players: list[PlayerAsset | None] = [asset_map.get(pid) for pid in get_player_ids]

    give_player_val = sum(value_player(p) for p in give_players if p)
    get_player_val = sum(value_player(p) for p in get_players if p)
    give_pick_val = sum(value_trade_pick(pid) for pid in give_pick_ids)
    get_pick_val = sum(value_trade_pick(pid) for pid in get_pick_ids)

    give_total = give_player_val + give_pick_val
    get_total = get_player_val + get_pick_val
    delta = get_total - give_total

    give_positions = [p.position for p in give_players if p]
    get_positions = [p.position for p in get_players if p]

    verdict_lean = (
        "ACCEPT (net positive)"
        if delta > 10
        else "DECLINE (net negative)"
        if delta < -10
        else "CLOSE (within 10 dynasty pts)"
    )

    vault_section = f"\n## Vault Research Notes\n{vault_notes}\n" if vault_notes else ""

    give_section = _format_side(give_players, give_pick_ids)
    get_section = _format_side(get_players, get_pick_ids)

    return f"""# Trade Evaluation — Dynasty Analysis

## Trade Summary
Give: {_side_label(give_player_ids, give_pick_ids)}
Get:  {_side_label(get_player_ids, get_pick_ids)}

## GIVE
{give_section}
  Subtotal: {give_total:.1f}  ({give_player_val:.1f} players + {give_pick_val:.1f} picks)

## GET
{get_section}
  Subtotal: {get_total:.1f}  ({get_player_val:.1f} players + {get_pick_val:.1f} picks)

## Net Value Differential
- Give total:  {give_total:.1f}
- Get total:   {get_total:.1f}
- Delta (get - give): {delta:+.1f}
- Quant lean: {verdict_lean}

## Roster Context
- Giving away: {", ".join(give_positions) if give_positions else "picks only"}
- Receiving:   {", ".join(get_positions) if get_positions else "picks only"}
- Net positional shift: {_position_delta(give_positions, get_positions)}
{vault_section}
## Your Task
1. Evaluate on **dynasty** value: long-term FPAR, age curve, positional scarcity.
2. Assess the pick vs. player tradeoff: is hoarding picks the correct strategy
   at this roster stage, or does this trade convert picks into a proven asset?
3. Flag any age/injury/usage risk that changes the quant reading.
4. Issue a verdict: **ACCEPT**, **DECLINE**, or **COUNTER** (with counter details).

Respond with:
- **Verdict**: ACCEPT / DECLINE / COUNTER + one-sentence rationale
- **Value read**: does the dynasty delta reflect the real trade, or does context override it?
- **Pick arbitrage**: should Rob hold picks or convert here?
- **Counter** (only if COUNTER): what asset swap makes this fair?

Post your finding via: ``sffm finding post --kind trade --body '<json>'``
where JSON has keys: ``verdict``, ``value_read``, ``pick_arbitrage``, ``counter`` (nullable).
"""
