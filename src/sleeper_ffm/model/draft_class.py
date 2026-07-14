"""Draft-class strength — the "is the 2027 class stacked?" signal, derived live.

The read is not hardcoded: it is computed from the FantasyCalc pick market, which
is re-pulled on every data refresh. For each upcoming season we compare what the
market pays for that class's picks against a *neutral* time-discounted baseline
(the same round bases and per-year discount the dynasty currency uses). A class the
market pays a premium for — above and beyond the normal one-year-out discount — is
one the crowd is treating as loaded; a discount means the opposite.

Because ``dynasty.value_pick`` already anchors every pick to the same FantasyCalc
per-season price, this strength is *already baked into* pick values, Draft Capital
grades, and trade numbers. This module exists to make that implicit signal visible
(and to degrade to "unrated" honestly when the market feed is unavailable), NOT to
re-multiply it into valuation — that would double-count.
"""

from __future__ import annotations

from dataclasses import dataclass

from sleeper_ffm.config import CURRENT_LEAGUE_YEAR


def _label(strength: float, rated: bool) -> str:
    """Human tier for the strength index; 'unrated' when the market feed is absent."""
    if not rated:
        return "UNRATED"
    if strength >= 1.08:
        return "STACKED"
    if strength >= 1.03:
        return "STRONG"
    if strength <= 0.90:
        return "WEAK"
    if strength < 0.97:
        return "SOFT"
    return "AVERAGE"


def _note(pct: float, rated: bool, imminent: bool) -> str:
    if not rated:
        return "No market pricing yet — neutral until these picks start trading."
    if imminent:
        return "Imminent class — the pick market prices these picks directly."
    if pct >= 3:
        return f"Market pays ~{pct:.0f}% over a neutral class this far out — treated as loaded."
    if pct <= -3:
        return f"Market prices this class ~{abs(pct):.0f}% light versus a neutral class."
    return "Market prices this class about average for its timeline."


@dataclass
class DraftClassStrength:
    """One upcoming draft class's market-implied strength read."""

    season: str
    strength: float  # index centered on ~1.0 (market vs neutral time-discounted base)
    pct: float  # (strength - 1) * 100, signed, for display
    label: str
    note: str
    rated: bool  # True when the market priced this class (else neutral default)
    source: str  # "fantasycalc" | "unavailable"


def _market_strength_ratio(season: str) -> float | None:
    """Average (live market price / neutral time-discounted base) across rounds.

    Returns None when the market has no price for any round of this season
    (never fabricates a ratio from nothing) — this is the single source of
    truth for class strength; ``dynasty.value_pick``'s fallback branch and
    ``build_draft_class_strength`` below both use it, so the number Rob sees
    on the Report Card always matches what (if ever) flows into valuation.
    """
    from sleeper_ffm.market.blend import market_pick_value
    from sleeper_ffm.model.dynasty import _PICK_ROUND_BASE, PICK_DISCOUNT_RATE

    decay = 1.0 - PICK_DISCOUNT_RATE
    try:
        years_out = max(0, int(season) - CURRENT_LEAGUE_YEAR)
    except ValueError:
        return None

    ratios: list[float] = []
    for round_, base in _PICK_ROUND_BASE.items():
        try:
            mv = market_pick_value(season, round_)
        except Exception:
            mv = None
        neutral = base * (decay**years_out)
        if mv is not None and neutral > 0:
            ratios.append(mv / neutral)

    if not ratios:
        return None
    # Clamp defensively: a single bad/thin data point shouldn't produce an
    # implausible multiplier once this feeds directly into pick valuation.
    avg = sum(ratios) / len(ratios)
    return round(max(0.5, min(2.0, avg)), 3)


def class_strength_for_season(season: str) -> float:
    """Public lookup: this season's market-implied class-strength multiplier.

    Returns 1.0 (neutral) when the market hasn't priced this season at all —
    safe to multiply into a valuation unconditionally.
    """
    ratio = _market_strength_ratio(season)
    return ratio if ratio is not None else 1.0


def build_draft_class_strength(seasons_ahead: int = 2) -> list[DraftClassStrength]:
    """Compute market-implied class strength for the current class through +N.

    Returns one entry per season. Never fabricates: a season the market hasn't
    priced comes back ``rated=False`` at a neutral 1.0.
    """
    out: list[DraftClassStrength] = []
    for i in range(seasons_ahead + 1):
        yr = str(CURRENT_LEAGUE_YEAR + i)
        ratio = _market_strength_ratio(yr)
        rated = ratio is not None
        strength = ratio if ratio is not None else 1.0
        source = "fantasycalc" if rated else "unavailable"

        pct = round((strength - 1.0) * 100, 1)
        out.append(
            DraftClassStrength(
                season=yr,
                strength=strength,
                pct=pct,
                label=_label(strength, rated),
                note=_note(pct, rated, imminent=(i == 0)),
                rated=rated,
                source=source,
            )
        )
    return out
