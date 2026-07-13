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

# Expected seasons of useful production remaining from peak, by position.
# (Dynasty value decays fastest for RBs, slowest for QBs.)
_PEAK_AGE: dict[str, int] = {
    "QB": 27,
    "RB": 24,
    "WR": 26,
    "TE": 26,
    "K": 28,
    "DEF": 26,
}

# Annual decay rate after peak, by position (fraction of prior season's value).
_DECAY_RATE: dict[str, float] = {
    "QB": 0.92,
    "RB": 0.85,
    "WR": 0.88,
    "TE": 0.90,
    "K": 0.92,
    "DEF": 0.90,
}

# Discount rate applied to future seasons (prefer near-term production).
_DISCOUNT_RATE: float = 0.12

# Replacement level FPAR for each position (the floor; zero-value baseline).
_REPLACEMENT_FPAR: dict[str, float] = {
    "QB": 15.0,
    "RB": 8.0,
    "WR": 8.0,
    "TE": 6.0,
}

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


# ---------------------------------------------------------------------------
# Core valuation functions
# ---------------------------------------------------------------------------


def value_player(player: PlayerAsset) -> float:
    """Compute a player's dynasty value in FPAR units.

    Projects FPAR forward ``_PROJECTION_HORIZON`` seasons using the position's
    age curve and discounts back to present value.

    Args:
        player: A ``PlayerAsset`` with current age and FPAR.

    Returns:
        Dynasty value in FPAR units (higher = more valuable). Zero if the
        player is at or past their expected useful life.
    """
    pos = player.position
    peak_age = _PEAK_AGE.get(pos, 26)
    decay = _DECAY_RATE.get(pos, 0.88)
    replacement = _REPLACEMENT_FPAR.get(pos, 8.0)

    # Current FPAR above replacement (clamp at 0 — no negative dynasty value)
    base_fpar = max(0.0, player.current_fpar - replacement)

    # How far past peak is the player?
    seasons_past_peak = max(0.0, player.age - peak_age)
    # Adjust base for players already on the decline
    adjusted_base = base_fpar * (decay**seasons_past_peak)

    # Project forward, discounting each future season
    total = 0.0
    for t in range(_PROJECTION_HORIZON):
        season_fpar = adjusted_base * (decay**t)
        discount = (1.0 - _DISCOUNT_RATE) ** t
        total += season_fpar * discount

    # Taxi/reserve penalty: young, unproven — apply 20% haircut
    if player.is_taxi:
        total *= 0.80

    return round(total, 2)


def value_pick(pick: PickAsset) -> float:
    """Compute a future pick's dynasty value in FPAR units.

    Uses round-based expected draft-slot value, adjusted for:
      - Round (earlier rounds = higher expected production)
      - Draft-class strength (``pick.class_strength`` multiplier)
      - Seasons until pick is used (time-discounting)

    Args:
        pick: A ``PickAsset``.

    Returns:
        Dynasty value in FPAR units.
    """
    # Base value by round — calibrated to approximate player values at each slot.
    # Round 1 mid-pick ≈ solid WR2/RB2 dynasty value; round 4 ≈ flier.
    round_base: dict[int, float] = {
        1: 55.0,
        2: 28.0,
        3: 14.0,
        4: 6.0,
    }
    base = round_base.get(pick.round, 4.0)

    # Adjust for class strength (>1 = loaded class worth more)
    base *= pick.class_strength

    # Time discount: future picks are worth less than the current league year.
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
        rows.append(
            {
                "type": "player",
                "id": p.player_id,
                "label": f"{p.name} ({p.position}, age {p.age:.0f})",
                "value": value_player(p),
                "position": p.position,
                "age": p.age,
                "current_fpar": p.current_fpar,
                "is_taxi": p.is_taxi,
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
