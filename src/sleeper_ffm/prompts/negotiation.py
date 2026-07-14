"""Negotiation copilot — how to pitch a specific trade to a specific owner.

The trade engine says *what* is fair; this says *how to get it done* with the human on
the other side. It packs everything known about the target player and the counterparty
owner — their archetype, contention window, positional needs and surplus — into a brief
with a concrete opening offer, a fair-value anchor, a walk-away ceiling, and talking
points tuned to how that owner actually thinks.

Deterministic where it can be (value bands off the dynasty model; needs off the dossier's
positional ranks), and it hands Claude the assembled facts to compose the actual pitch —
the same "engine builds the prompt, Claude reasons" split the rest of the app uses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Value bands as multiples of the target's fair dynasty value.
_OPENING_MULT: float = 0.85  # first offer: lowball but not insulting
_WALKAWAY_MULT: float = 1.18  # most I'd part with before it's a bad deal
# A positional rank in the bottom third of the league reads as a need; top third, surplus.
_NEED_QUANTILE: float = 0.67
_SURPLUS_QUANTILE: float = 0.33


@dataclass
class NegotiationBrief:
    """Packed facts + a ready-to-reason prompt for one trade approach."""

    target_player: str
    target_position: str
    target_value: float
    owner_name: str
    owner_archetype: str
    owner_window: str
    owner_needs: list[str]
    owner_surplus: list[str]
    opening_value: float
    fair_value: float
    walkaway_value: float
    talking_points: list[str]
    prompt: str
    warnings: list[str] = field(default_factory=list)


def negotiation_angles(archetype: str, window: str, target_position: str) -> list[str]:
    """Owner-psychology talking points from archetype + contention window. Pure.

    Args:
        archetype: The dossier archetype label (case-insensitive substring match).
        window: The owner's contention-window label (e.g. WIN-NOW, REBUILD).
        target_position: Position of the player I'm trying to acquire.

    Returns:
        Concrete angles to lead with, tuned to how this owner values assets.
    """
    a = (archetype or "").lower()
    w = (window or "").upper()
    points: list[str] = []

    if "youth" in a or "future" in a or "rebuild" in a:
        points.append("Lead with youth and picks — this owner overweights age and future capital.")
    if "win" in a or "contend" in a or "star" in a:
        points.append("Emphasize immediate starting value; they pay up for proven production.")
    if "value" in a or "shark" in a or "active" in a:
        points.append("Come in near-fair and cite numbers — a savvy trader spots a lowball fast.")

    if "WIN-NOW" in w or "SUSTAIN" in w:
        points.append(
            "They're contending: package a plug-and-play starter, ask for their future picks."
        )
    elif "REBUILD" in w or "RETOOL" in w:
        points.append(
            "They're rebuilding: offer picks and youth, pry the win-now piece you actually want."
        )
    else:
        points.append("Muddled window — frame the deal as helping them decide which way to lean.")

    points.append(
        f"Anchor the {target_position} conversation on scarcity: remind them what replacing "
        "this production costs on the market."
    )
    return points


def _needs_and_surplus(position_ranks: list) -> tuple[list[str], list[str]]:
    """Split an owner's positions into needs (weak ranks) and surplus (strong ranks)."""
    needs: list[str] = []
    surplus: list[str] = []
    for pr in position_ranks:
        pos = getattr(pr, "position", None) or (
            pr.get("position") if isinstance(pr, dict) else None
        )
        rank = getattr(pr, "rank", None) or (pr.get("rank") if isinstance(pr, dict) else None)
        of = getattr(pr, "of", None) or (pr.get("of") if isinstance(pr, dict) else None)
        if not pos or not rank or not of:
            continue
        quantile = rank / of
        if quantile >= _NEED_QUANTILE:
            needs.append(pos)
        elif quantile <= _SURPLUS_QUANTILE:
            surplus.append(pos)
    return needs, surplus


def build_negotiation_brief(target_player_id: str, owner_roster_id: int) -> NegotiationBrief:
    """Build a negotiation brief for acquiring a player from a given owner.

    Returns:
        A :class:`NegotiationBrief`. Raises ValueError if the target or owner is unknown.
    """
    from sleeper_ffm.config import DEFAULT_VALUE_SEASON
    from sleeper_ffm.model.dynasty import value_player
    from sleeper_ffm.model.owner_dossier import build_dossier
    from sleeper_ffm.model.valuation import build_player_assets
    from sleeper_ffm.sleeper.client import SleeperClient

    warnings: list[str] = []
    with SleeperClient() as c:
        players = c.players()
    meta = players.get(target_player_id)
    if meta is None:
        raise ValueError(f"Unknown target player {target_player_id}")

    assets = build_player_assets(seasons=[DEFAULT_VALUE_SEASON], sleeper_players=players)
    asset = next((a for a in assets if a.player_id == target_player_id), None)
    fair_value = round(value_player(asset), 1) if asset else 0.0
    if asset is None:
        warnings.append("Target not in the valued pool; value defaults to 0 (unproven/rookie).")

    dossier = build_dossier(owner_roster_id)
    needs, surplus = _needs_and_surplus(getattr(dossier, "position_ranks", []) or [])
    window = getattr(getattr(dossier, "contention", None), "window", "") or ""
    talking = negotiation_angles(dossier.archetype, window, meta.get("position") or "?")

    opening = round(fair_value * _OPENING_MULT, 1)
    walkaway = round(fair_value * _WALKAWAY_MULT, 1)
    target_name = meta.get("full_name") or target_player_id

    prompt = f"""## TRADE NEGOTIATION — acquire {target_name} from {dossier.display_name}

### Target
{target_name} ({meta.get("position")} {meta.get("team")}) — fair dynasty value ~{fair_value:.0f}.

### Counterparty ({dossier.display_name})
- Archetype: {dossier.archetype} — {dossier.archetype_rationale}
- Contention window: {window or "unclassified"}
- Roster needs (weak positions): {", ".join(needs) or "none obvious"}
- Surplus (strong positions): {", ".join(surplus) or "none obvious"}
- Avg age {dossier.avg_age:.1f}, top-heavy {dossier.top_heavy_pct:.0%}

### Value bands (send-side, in dynasty units)
- Opening offer: ~{opening:.0f} (lowball but credible)
- Fair anchor: ~{fair_value:.0f}
- Walk-away ceiling: ~{walkaway:.0f} (do not exceed)

### Owner-tuned angles
{chr(10).join(f"- {p}" for p in talking)}

### Request
Draft the actual pitch: the specific opening package (from MY surplus that fills THEIR
needs), the fallback if they counter, and the one sentence that lands this deal with this
owner. Do not exceed the walk-away value. Post via `sffm finding negotiation --body '<json>'`
with keys: `opening_package`, `fallback`, `closing_line`, `max_send_value`.
"""
    return NegotiationBrief(
        target_player=target_name,
        target_position=meta.get("position") or "?",
        target_value=fair_value,
        owner_name=dossier.display_name,
        owner_archetype=dossier.archetype,
        owner_window=window,
        owner_needs=needs,
        owner_surplus=surplus,
        opening_value=opening,
        fair_value=fair_value,
        walkaway_value=walkaway,
        talking_points=talking,
        prompt=prompt,
        warnings=warnings,
    )
