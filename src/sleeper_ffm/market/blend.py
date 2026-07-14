"""Market anchor and divergence from FPAR model.

Provides two functions:

- ``market_anchor()``: best available {sleeper_id: market_value} dict,
  trying FantasyCalc first and falling back to DynastyProcess.
- ``divergence(anchor, model)``: {sleeper_id: pct_diff} where positive means
  the model rates the player higher than the market.

Both use the same 0-10000 FantasyCalc value scale; DynastyProcess values are
on the same order of magnitude so no rescaling is needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sleeper_ffm.cache import ttl_cache

log = logging.getLogger(__name__)

# Minimum number of players required for a source to be considered "usable".
_MIN_USABLE = 200

# Canonical FantasyCalc (0-10000) → annual-FPAR conversion factor. Single source of
# truth for rookie pricing. Derived empirically:
# FC top-WR (~8500) ≈ 110 annual FPAR → ~77; calibrated to 78.
FC_TO_FPAR_SCALE: float = 78.0

# Fixed FantasyCalc → dynasty-value scale, used for STEAL/REACH labels where a
# stable population reference is required (an empirical per-board scale would
# center the board's own ratio at zero divergence). Median of value_player/fc
# over the rostered universe ≈ 0.066 (2026-07 snapshot).
FC_TO_DYNASTY_SCALE: float = 0.066

# Default model/market blend weights. Dynasty best practice (KTC / FantasyCalc /
# FantasyPros consensus, 2026) treats the market as the anchor and the model as a
# bounded context overlay — ~65% market / ~35% model, not an even split.
_DEFAULT_MODEL_WEIGHT: float = 0.35
_DEFAULT_MARKET_WEIGHT: float = 0.65
_BLEND_CALIBRATION: str = "MARKET-ANCHORED-65-35"


def market_anchor() -> dict[str, float]:
    """Return the best available dynasty market values keyed by Sleeper ID.

    Tries FantasyCalc first; falls back to DynastyProcess if FC returns fewer
    than ``_MIN_USABLE`` entries (indicating a fetch failure).

    Returns:
        {sleeper_id: value} mapping where value is on a ~0-10000 scale.
        Empty dict if both sources fail.
    """
    from sleeper_ffm.market import dynastyprocess, fantasycalc

    fc = fantasycalc.fetch()
    if len(fc) >= _MIN_USABLE:
        log.info("market_anchor: using FantasyCalc (%d players)", len(fc))
        return fc

    log.warning(
        "market_anchor: FantasyCalc returned %d entries, falling back to DynastyProcess", len(fc)
    )
    dp = dynastyprocess.fetch()
    if len(dp) >= _MIN_USABLE:
        log.info("market_anchor: using DynastyProcess (%d players)", len(dp))
        return dp

    log.error("market_anchor: both sources failed (FC=%d, DP=%d)", len(fc), len(dp))
    return {}


def pick_market_values() -> dict[tuple[str, int], float]:
    """Return FC pick values for use in pick_market arbitrage analysis.

    Falls back to an empty dict when FantasyCalc is unavailable, allowing the
    pick_market module to degrade gracefully to model-only mode.

    Returns:
        {(season_str, round_int): fc_value} or {} if FC is down.
    """
    from sleeper_ffm.market import fantasycalc

    return fantasycalc.fetch_picks()


def pick_market_available() -> bool:
    """Whether the FantasyCalc pick-value feed is currently reachable and populated.

    Distinct from "this specific pick isn't priced" (normal — e.g. a season far
    enough out that FC hasn't listed it): this is the coarser "is the feed down
    at all" signal, so callers can flag a real outage rather than a routine gap.
    """
    from sleeper_ffm.market import fantasycalc

    return bool(fantasycalc.fetch_picks())


@ttl_cache()
def market_pick_value(season: str, round_: int) -> float | None:
    """Market value of a draft pick in the SAME dynasty units as players.

    FantasyCalc pick values scaled by ``FC_TO_DYNASTY_SCALE`` so a pick and a
    player are directly comparable — the anchor that keeps trade math honest
    (an early 1st ≈ one RB1 / mid-WR2, per 2026 dynasty consensus).

    Returns:
        Dynasty-unit value, or None when the market has no price for the pick.
    """
    from sleeper_ffm.market import fantasycalc

    fc = fantasycalc.fetch_picks().get((str(season), int(round_)))
    return round(fc * FC_TO_DYNASTY_SCALE, 2) if fc is not None else None


# Positions the FPAR model cannot value and must blend market-only. In a 1QB
# league the QB replacement level (QB10-12) sits near the top of the position,
# so pocket QBs net ~0 FPAR while rushing QBs clear it — the model's within-QB
# ranking disagrees with reality, so QB is priced off the market alone. (Revisit
# if this ever becomes a superflex league, where QB FPAR regains meaning.)
_MARKET_ONLY_POSITIONS: frozenset[str] = frozenset({"QB"})
# Model values at or below this mean "the model can't value this player"
# (replacement-level / unscored). Such players are excluded from the ranking and
# priced market-only, so the long tail of zeroed scrubs can't inflate the
# percentile of a genuinely rostered player.
_MODEL_FLOOR: float = 1.0
# A position needs at least this many model-valued players before the model's
# within-position ranking is used; below it the blend is market-only.
_MIN_VALUED_PER_POS: int = 4


@dataclass(frozen=True)
class MarketBlend:
    """Position-aware, rank-based context for blending model value with market.

    Model FPAR is not comparable across positions (a 1QB league's replacement
    level zeroes elite QBs and inflates RBs) and a single per-position scale
    factor overshoots players whose model/market ratio differs from the position
    median. So the market — cross-positionally sane — is the value scale, and the
    model contributes only a *within-position ranking*: a player's model rank is
    mapped to the market value at that rank, then blended with the player's own
    market value. The result is always bounded by the position's market range.

    Blended values are precomputed per pool player in ``values``; ``blended_value``
    is a lookup with a model-only fallback for players outside the pool.
    """

    market: dict[str, float]  # raw FantasyCalc values by sleeper id
    fc_scale: float  # FC value → dynasty display units
    values: dict[str, float]  # precomputed blended value per pool player
    market_valued: frozenset[str]  # pool players where the market contributed
    calibration: str = _BLEND_CALIBRATION
    model_valued_only: bool = False

    def market_dyn(self, player_id: str) -> float | None:
        """Return a player's market value in dynasty display units, or None."""
        fc = self.market.get(player_id)
        return None if fc is None else fc * self.fc_scale


def _percentile_rank(sorted_vals: list[float], value: float) -> float:
    """Fraction of ``sorted_vals`` at or below ``value`` (0-1)."""
    import bisect

    n = len(sorted_vals)
    if n == 0:
        return 0.5
    return bisect.bisect_right(sorted_vals, value) / n


def _value_at_percentile(sorted_vals: list[float], pct: float) -> float:
    """Interpolate the value at percentile ``pct`` (0-1) of a sorted list."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_vals[0]
    idx = pct * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def build_market_blend(
    model_values: dict[str, float],
    positions: dict[str, str],
    market: dict[str, float] | None = None,
    model_weight: float = _DEFAULT_MODEL_WEIGHT,
    market_weight: float = _DEFAULT_MARKET_WEIGHT,
) -> MarketBlend:
    """Build a rank-based, position-aware blend context.

    Args:
        model_values: {sleeper_id: model_dynasty_value} for a representative pool.
        positions: {sleeper_id: position} for the same pool.
        market: {sleeper_id: fc_value}; fetched via ``market_anchor()`` if None.
        model_weight: Weight on the model's ranking opinion (0-1).
        market_weight: Weight on the player's own market value (0-1).

    Returns:
        A :class:`MarketBlend` with precomputed blended values. If the market
        anchor is empty, the blend is model-only and never alters values.
    """
    market = market if market is not None else market_anchor()
    if not market:
        log.warning("build_market_blend: no market anchor; blend degrades to model-only")
        return MarketBlend(
            market={},
            fc_scale=FC_TO_DYNASTY_SCALE,
            values={},
            market_valued=frozenset(),
            model_valued_only=True,
        )

    # Group each position's pool players as (pid, model, market_dyn).
    by_pos: dict[str, list[tuple[str, float, float]]] = {}
    for pid, model in model_values.items():
        fc = market.get(pid)
        pos = positions.get(pid)
        if fc and fc > 0 and pos:
            by_pos.setdefault(pos, []).append((pid, model, fc * FC_TO_DYNASTY_SCALE))

    values: dict[str, float] = {}
    market_valued: set[str] = set()
    for pos, members in by_pos.items():
        # Rank only among players the model can actually value; map onto THEIR
        # market distribution so zeroed scrubs can't inflate anyone's percentile.
        valued = [(pid, m, md) for pid, m, md in members if m > _MODEL_FLOOR]
        market_only = pos in _MARKET_ONLY_POSITIONS or len(valued) < _MIN_VALUED_PER_POS
        if not market_only:
            models_sorted = sorted(m for _, m, _ in valued)
            markets_sorted = sorted(md for _, _, md in valued)
        for pid, model, md in members:
            if market_only or model <= _MODEL_FLOOR:
                blended = md  # market-only: degenerate position or model-unvalued player
            else:
                model_opinion = _value_at_percentile(
                    markets_sorted, _percentile_rank(models_sorted, model)
                )
                blended = model_weight * model_opinion + market_weight * md
            values[pid] = round(blended, 2)
            market_valued.add(pid)

    log.info("build_market_blend: blended %d pool players across %d positions",
             len(values), len(by_pos))
    return MarketBlend(
        market=market,
        fc_scale=FC_TO_DYNASTY_SCALE,
        values=values,
        market_valued=frozenset(market_valued),
    )


def build_player_blend(
    assets: list,
    market: dict[str, float] | None = None,
    model_weight: float = _DEFAULT_MODEL_WEIGHT,
    market_weight: float = _DEFAULT_MARKET_WEIGHT,
) -> MarketBlend:
    """Build a :class:`MarketBlend` from a list of ``PlayerAsset`` objects.

    Convenience wrapper that computes model dynasty values via
    ``dynasty.value_player`` and the position map from the same pool.

    Args:
        assets: PlayerAsset objects (a representative valuation pool).
        market: {sleeper_id: fc_value}; fetched via ``market_anchor()`` if None.
        model_weight: Weight on the model value (0-1).
        market_weight: Weight on the market value (0-1).

    Returns:
        A :class:`MarketBlend`.
    """
    from sleeper_ffm.model.dynasty import value_player

    model_values = {a.player_id: value_player(a) for a in assets}
    positions = {a.player_id: a.position for a in assets}
    return build_market_blend(model_values, positions, market, model_weight, market_weight)


def blended_value(
    player_id: str, position: str, model_value: float, blend: MarketBlend
) -> tuple[float, bool]:
    """Return a player's precomputed blended value (position-aware, rank-based).

    Args:
        player_id: Sleeper player ID.
        position: Player position (unused for the lookup; kept for call-site clarity).
        model_value: The model's dynasty value — used only as the fallback when the
            player is outside the blend pool.
        blend: A :class:`MarketBlend` context.

    Returns:
        ``(value, market_valued)`` — the blended value, and whether the market
        contributed (False = model-only fallback for a non-pool player).
    """
    if player_id in blend.values:
        return blend.values[player_id], player_id in blend.market_valued
    return round(model_value, 2), False


def divergence(
    anchor: dict[str, float],
    model: dict[str, float],
) -> dict[str, float]:
    """Compute per-player divergence between model and market.

    Both ``anchor`` and ``model`` must use the same Sleeper ID keys. If the
    scales differ (model in FPAR, anchor in FC units), the caller is responsible
    for normalizing — this function only computes relative percent difference.

    Args:
        anchor: Market values {sleeper_id: market_value}.
        model: Model values {sleeper_id: model_value}.

    Returns:
        {sleeper_id: pct_diff} where positive = model rates player above market,
        negative = model rates player below market. Players in only one source
        are excluded.
    """
    result: dict[str, float] = {}
    for sid in anchor.keys() & model.keys():
        mkt = anchor[sid]
        mdl = model[sid]
        if mkt == 0:
            continue
        result[sid] = round((mdl - mkt) / abs(mkt) * 100, 1)
    return result
