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

log = logging.getLogger(__name__)

# Minimum number of players required for a source to be considered "usable".
_MIN_USABLE = 200


def market_anchor() -> dict[str, float]:
    """Return the best available dynasty market values keyed by Sleeper ID.

    Tries FantasyCalc first; falls back to DynastyProcess if FC returns fewer
    than ``_MIN_USABLE`` entries (indicating a fetch failure).

    Returns:
        {sleeper_id: value} mapping where value is on a ~0-10000 scale.
        Empty dict if both sources fail.
    """
    from sleeper_ffm.market import fantasycalc, dynastyprocess

    fc = fantasycalc.fetch()
    if len(fc) >= _MIN_USABLE:
        log.info("market_anchor: using FantasyCalc (%d players)", len(fc))
        return fc

    log.warning("market_anchor: FantasyCalc returned %d entries, falling back to DynastyProcess", len(fc))
    dp = dynastyprocess.fetch()
    if len(dp) >= _MIN_USABLE:
        log.info("market_anchor: using DynastyProcess (%d players)", len(dp))
        return dp

    log.error("market_anchor: both sources failed (FC=%d, DP=%d)", len(fc), len(dp))
    return {}


# Historical average FC pick values by round, calibrated from 2023-2025 samples.
# Used as the baseline for class_strength_for_season() when FC pick data is thin.
_HISTORICAL_PICK_VALUE: dict[int, float] = {
    1: 6500.0,
    2: 3500.0,
    3: 1800.0,
    4: 700.0,
}


def class_strength_for_season(season: str) -> float:
    """Return a class-strength multiplier for a given season's rookie picks.

    Derives the multiplier from FantasyCalc pick values relative to the
    historical average per round. A loaded rookie class (e.g. 2024 WR depth)
    scores > 1.0; a weak class scores < 1.0.

    Falls back to 1.0 when FC pick data is unavailable or the season is not
    present.

    Args:
        season: Season string, e.g. "2026".

    Returns:
        Multiplier to use as ``PickAsset.class_strength``.
    """
    from sleeper_ffm.market import fantasycalc

    picks = fantasycalc.fetch_picks()
    if not picks:
        return 1.0

    season_picks = {round_: val for (s, round_), val in picks.items() if s == season}
    if not season_picks:
        return 1.0

    ratios = []
    for round_, val in season_picks.items():
        hist = _HISTORICAL_PICK_VALUE.get(round_)
        if hist and hist > 0:
            ratios.append(val / hist)

    if not ratios:
        return 1.0

    multiplier = sum(ratios) / len(ratios)
    return round(max(0.5, min(2.0, multiplier)), 3)


def pick_market_values() -> dict[tuple[str, int], float]:
    """Return FC pick values for use in pick_market arbitrage analysis.

    Falls back to an empty dict when FantasyCalc is unavailable, allowing the
    pick_market module to degrade gracefully to model-only mode.

    Returns:
        {(season_str, round_int): fc_value} or {} if FC is down.
    """
    from sleeper_ffm.market import fantasycalc

    return fantasycalc.fetch_picks()


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
