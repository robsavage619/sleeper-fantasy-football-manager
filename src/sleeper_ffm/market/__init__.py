"""Market data backbone — external dynasty valuations as a ground-truth anchor.

FantasyCalc is the primary source (dynasty trade market prices, updated daily).
DynastyProcess is the fallback (community-curated rankings, weekly CSV).

Public API::

    from sleeper_ffm.market import market_anchor, divergence

    anchor = market_anchor()           # {sleeper_id: market_value, ...}
    div = divergence(anchor, model)    # {sleeper_id: pct_diff, ...}
"""

from __future__ import annotations

from sleeper_ffm.market.blend import class_strength_for_season, divergence, market_anchor, pick_market_values

__all__ = ["class_strength_for_season", "divergence", "market_anchor", "pick_market_values"]
