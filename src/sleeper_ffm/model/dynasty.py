"""Dynasty asset model — players, keepers, and future picks in one currency.

Every tradeable asset in a dynasty league has a value denominated in the same
unit: *expected fantasy points above replacement over the asset's remaining
useful life, discounted to present value*. Players are scored by their
projected career trajectory; picks are valued by expected draft-slot x expected
production at that slot x draft-class strength.

This module computes:
    - ``value_player``  — single player's dynasty value
    - ``value_pick``    — single pick's dynasty value
    - ``roster_table``  — full roster valued (players + taxi + reserve + keepers)
    - ``asset_table``   — roster + traded picks the team holds (full trade currency)

Values are in *fantasy points above replacement per season* (FPAR), scaled so
that a typical WR1 is ~100 FPAR. Exact calibration is updated empirically from
the nflverse backfill once the first ``sffm ingest`` run completes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sleeper_ffm.config import CURRENT_LEAGUE_YEAR

# ---------------------------------------------------------------------------
# Age curves (empirical priors — updated from nflverse backfill)
# These represent expected peak-to-decline shape; values are multiplicative
# factors on a player's current FPAR estimate.
# ---------------------------------------------------------------------------

# Age at which each position typically reaches peak production (2026 dynasty
# aging-curve consensus: Fantasy Points / Apex / FSCollective). RB prime is years
# 2-6 (~22-26); WR/TE peak ~26-27; QB flat and late (28-33). Note: QB is priced
# market-only in the blend, so its curve only shapes model-side ranking.
_PEAK_AGE: dict[str, int] = {
    "QB": 29,
    "RB": 25,
    "WR": 27,
    "TE": 26,
    "K": 28,
    "DEF": 26,
}

# Annual decay rate after peak, by position (fraction of prior season's value).
# RB is the steepest — the research describes a post-~28 cliff, not a gentle ramp;
# WR/TE decline slowly with a longer tail; QB is the flattest.
_DECAY_RATE: dict[str, float] = {
    "QB": 0.94,
    "RB": 0.82,
    "WR": 0.90,
    "TE": 0.88,
    "K": 0.92,
    "DEF": 0.90,
}

# Conservative pre-peak growth rate — how much FPAR grows per season toward peak.
# Market blend (Phase 1) carries most of the youth premium; this handles the rest.
_ASCENT_RATE: dict[str, float] = {
    "QB": 1.05,
    "RB": 1.04,
    "WR": 1.06,
    "TE": 1.06,
}

# Discount rate applied to future seasons (prefer near-term production).
_DISCOUNT_RATE: float = 0.12

# Canonical per-year discount for future picks, shared with the pick-market model
# so both price a pick with the same decay.
PICK_DISCOUNT_RATE: float = _DISCOUNT_RATE

# Seasons to project forward when computing dynasty value.
_PROJECTION_HORIZON: int = 8


@dataclass
class PlayerAsset:
    """A rostered player as a dynasty asset."""

    player_id: str
    name: str
    position: str
    age: float  # decimal age (years)
    current_fpar: float  # fantasy points above replacement, last full season
    team: str = ""
    is_taxi: bool = False
    is_reserve: bool = False


@dataclass
class PickAsset:
    """A future draft pick as a dynasty asset."""

    season: str  # e.g. "2027"
    round: int  # 1-4 in a 4-round dynasty draft
    original_owner_id: int  # roster_id that originally owned the pick
    current_owner_id: int  # roster_id currently holding the pick
    pick_number: int | None = None  # exact slot if known (post-draft)
    class_strength: float = 1.0  # multiplier: >1 = loaded class, <1 = weak


@dataclass
class RosterAssets:
    """All dynasty assets controlled by one team."""

    roster_id: int
    owner_id: str
    players: list[PlayerAsset] = field(default_factory=list)
    picks: list[PickAsset] = field(default_factory=list)

    @property
    def player_value(self) -> float:
        """Total dynasty value of rostered players."""
        return sum(value_player(p) for p in self.players)

    @property
    def pick_value(self) -> float:
        """Total dynasty value of held future picks."""
        return sum(value_pick(p) for p in self.picks)

    @property
    def total_value(self) -> float:
        """Combined player + pick dynasty value."""
        return self.player_value + self.pick_value


# Years past positional peak before a player is "structurally declining" rather than
# just having a down year — regression/leverage math assumes stable underlying talent,
# which stops holding once a player is this deep past peak (e.g. a 41yo QB throwing
# for fewer yards than expected is aging, not unlucky).
_AGE_DECLINE_BUFFER: int = 8


def is_age_declining(position: str, age: float | None) -> bool:
    """Whether a player is far enough past positional peak to discount buy-low signals.

    Args:
        position: Player position.
        age: Player age in years, or ``None`` if unknown (never flagged).

    Returns:
        True if ``age`` is at least :data:`_AGE_DECLINE_BUFFER` years past the
        position's typical peak age.
    """
    if age is None:
        return False
    return age >= _PEAK_AGE.get(position, 26) + _AGE_DECLINE_BUFFER


# ---------------------------------------------------------------------------
# Core valuation functions
# ---------------------------------------------------------------------------


@dataclass
class ValueBreakdown:
    """Named components behind a dynasty value, for UI display.

    ``value`` is the same number ``value_player`` returns. ``current_fpar`` is
    what the player produced last season; ``age_curve_adjustment`` is how much
    the projection added (aging into a young ascent) or subtracted (aging out
    of a decline) on top of that, before the taxi discount.
    """

    value: float
    current_fpar: float
    age_curve_adjustment: float
    implied_peak_fpar: float
    career_phase: str  # "ascending" | "at-peak" | "declining"
    seasons_from_peak: float


def _project_value(player: PlayerAsset) -> tuple[float, float, str, float]:
    """Shared projection core for ``value_player`` and ``value_player_breakdown``.

    Returns:
        ``(total_before_taxi_discount, implied_peak, career_phase, seasons_from_peak)``.
    """
    pos = player.position
    peak_age = _PEAK_AGE.get(pos, 26)
    decay = _DECAY_RATE.get(pos, 0.88)
    ascent = _ASCENT_RATE.get(pos, 1.05)

    base_fpar = max(0.0, player.current_fpar)
    if base_fpar == 0.0:
        return 0.0, 0.0, "at-peak", 0.0

    # Back-solve implied peak FPAR from current production and career stage.
    # For post-peak: current = peak * decay^seasons_past → peak = current / decay^n
    # For pre-peak: peak will be current * ascent^seasons_remaining
    seasons_past_peak = max(0.0, player.age - peak_age)
    seasons_to_peak = max(0.0, peak_age - player.age)

    if seasons_past_peak > 0:
        implied_peak = base_fpar / (decay**seasons_past_peak)
    else:
        implied_peak = base_fpar * (ascent**seasons_to_peak)

    # Project each future season from implied peak.
    # seasons_past at projected age = (player.age + 1 + t) - peak_age
    total = 0.0
    for t in range(_PROJECTION_HORIZON):
        projected_age = player.age + 1 + t
        seasons_past = projected_age - peak_age
        if seasons_past >= 0:
            season_fpar = implied_peak * (decay**seasons_past)
        else:
            # Still pre-peak in projected year: fpar < implied_peak
            seasons_before = -seasons_past
            season_fpar = implied_peak / (ascent**seasons_before)
        discount = (1.0 - _DISCOUNT_RATE) ** t
        total += season_fpar * discount

    seasons_from_peak = player.age - peak_age
    phase = (
        "ascending" if seasons_from_peak < -0.5 else "declining" if seasons_from_peak > 0.5
        else "at-peak"
    )
    return total, implied_peak, phase, seasons_from_peak


def value_player(player: PlayerAsset) -> float:
    """Compute a player's dynasty value in FPAR units.

    Projects FPAR forward ``_PROJECTION_HORIZON`` seasons using the position's
    age curve (pre-peak ascent + post-peak decay) and discounts back to present
    value.

    The model back-solves an implied peak FPAR from current production and career
    stage, then projects each future season relative to that implied peak. Pre-peak
    players benefit from growth toward peak; post-peak players see continuous decay.

    Args:
        player: A ``PlayerAsset`` with current age and FPAR.

    Returns:
        Dynasty value in FPAR units (higher = more valuable). Zero for
        replacement-level or below-replacement players.
    """
    total, _implied_peak, _phase, _seasons_from_peak = _project_value(player)
    if player.is_taxi:
        total *= 0.80
    return round(total, 2)


def value_player_breakdown(player: PlayerAsset) -> ValueBreakdown:
    """Decompose a player's dynasty value into current production vs. age-curve.

    Same projection as ``value_player``, exposed as named components so a UI
    can show *why* a value is what it is instead of a single opaque float.

    Args:
        player: A ``PlayerAsset`` with current age and FPAR.

    Returns:
        A :class:`ValueBreakdown`.
    """
    total, implied_peak, phase, seasons_from_peak = _project_value(player)
    if player.is_taxi:
        total *= 0.80
    value = round(total, 2)
    current_fpar = round(max(0.0, player.current_fpar), 2)
    return ValueBreakdown(
        value=value,
        current_fpar=current_fpar,
        age_curve_adjustment=round(value - current_fpar, 2),
        implied_peak_fpar=round(implied_peak, 2),
        career_phase=phase,
        seasons_from_peak=round(seasons_from_peak, 1),
    )


# Fallback round-base pick values in dynasty units, calibrated to the 2026 market
# (an early 1st ≈ one RB1 / mid-WR2; values fall off a cliff after round 1). Used
# only when the live FantasyCalc pick market has no price for the pick.
_PICK_ROUND_BASE: dict[int, float] = {1: 190.0, 2: 100.0, 3: 68.0, 4: 52.0}


def value_pick(pick: PickAsset) -> float:
    """Compute a future pick's dynasty value, market-anchored.

    Picks are priced off the live FantasyCalc pick market (same dynasty units as
    players) so a pick and a player are directly comparable — critical in a league
    where 90% of trades involve picks. Falls back to a market-calibrated round
    base (with class-strength and time-discount adjustments) only when the market
    has no price for the pick.

    Class strength (how loaded a season's rookie class is) is NOT applied on top
    of the live market branch below — a market price already reflects the
    crowd's read on that class, so multiplying it again would double-count. It
    IS applied in the fallback branch, which has no market signal to draw on
    otherwise and would be class-blind without it. Uses the same computation
    ``model.draft_class`` surfaces on the Report Card, so the two never disagree.

    Args:
        pick: A ``PickAsset``.

    Returns:
        Dynasty value in the same units as ``value_player``.
    """
    from sleeper_ffm.market.blend import market_pick_value
    from sleeper_ffm.model.draft_class import class_strength_for_season

    market = market_pick_value(pick.season, pick.round)
    if market is not None:
        return round(market * pick.class_strength, 2)

    base = _PICK_ROUND_BASE.get(pick.round, 30.0) * pick.class_strength
    base *= class_strength_for_season(pick.season)
    try:
        seasons_out = max(0, int(pick.season) - CURRENT_LEAGUE_YEAR)
    except ValueError:
        seasons_out = 1
    discount = (1.0 - _DISCOUNT_RATE) ** seasons_out
    return round(base * discount, 2)


# ---------------------------------------------------------------------------
# Roster + league asset tables
# ---------------------------------------------------------------------------


def asset_table(roster: RosterAssets) -> list[dict]:
    """Return a flat list of all assets with their individual dynasty values.

    Args:
        roster: A ``RosterAssets`` instance.

    Returns:
        List of dicts, each with ``type``, ``id``, ``label``, ``value``.
        Sorted by value descending.
    """
    rows: list[dict] = []
    for p in roster.players:
        breakdown = value_player_breakdown(p)
        rows.append(
            {
                "type": "player",
                "id": p.player_id,
                "label": f"{p.name} ({p.position}, age {p.age:.0f})",
                "value": breakdown.value,
                "position": p.position,
                "age": p.age,
                "current_fpar": p.current_fpar,
                "is_taxi": p.is_taxi,
                "age_curve_adjustment": breakdown.age_curve_adjustment,
                "career_phase": breakdown.career_phase,
            }
        )
    for pk in roster.picks:
        rows.append(
            {
                "type": "pick",
                "id": f"{pk.season}_R{pk.round}",
                "label": f"{pk.season} Round {pk.round}",
                "value": value_pick(pk),
                "season": pk.season,
                "round": pk.round,
                "class_strength": pk.class_strength,
            }
        )
    return sorted(rows, key=lambda x: x["value"], reverse=True)
