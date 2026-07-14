from __future__ import annotations

import logging
from dataclasses import dataclass

from sleeper_ffm.config import CURRENT_LEAGUE_YEAR, LEAGUE_ID
from sleeper_ffm.market.blend import market_pick_value
from sleeper_ffm.model.dynasty import _PICK_ROUND_BASE, PICK_DISCOUNT_RATE
from sleeper_ffm.sleeper.client import SleeperClient

log = logging.getLogger(__name__)

# Model production-expectation base, in the SAME dynasty units as the market
# (so the divergence below is a true apples-to-apples comparison, not the old
# fc/78-vs-fc*0.066 scale mismatch that made every pick read BUY).
_BASE: dict[int, float] = dict(_PICK_ROUND_BASE)
_CURRENT_YEAR = CURRENT_LEAGUE_YEAR
# Same per-year discount the dynasty currency applies to future picks, so the
# arbitrage detector and the trade currency price a pick identically.
_DECAY = 1.0 - PICK_DISCOUNT_RATE
_FUTURE_SEASONS = ["2027", "2028"]
_ALL_ROUNDS = [1, 2, 3, 4]


@dataclass
class PickMarketSignal:
    """Model-vs-market valuation signal for a single (season, round) pick."""

    season: str
    round: int
    model_value: float
    market_value: float
    discount_pct: float
    signal: str
    rationale: str
    trade_count: int
    market_source: str  # "fantasycalc" or "trade-frequency"


def _model_value(season: str, round_: int) -> float:
    years_ahead = max(0, int(season) - _CURRENT_YEAR)
    return _BASE[round_] * (_DECAY**years_ahead)


def _market_value_from_trades(model_val: float, trade_count: int) -> tuple[float, str]:
    """Fallback: estimate market value from trade frequency (circular but graceful)."""
    if trade_count == 0:
        return model_val * 0.90, "trade-frequency"
    raw = model_val * (0.80 + 0.05 * min(trade_count, 6))
    return min(raw, model_val * 1.1), "trade-frequency"


def _signal(discount_pct: float) -> str:
    if discount_pct < -0.15:
        return "BUY"
    if discount_pct > 0.15:
        return "SELL"
    return "HOLD"


def _rationale(season: str, round_: int, discount_pct: float, trade_count: int, sig: str) -> str:
    pct_label = f"{abs(discount_pct) * 100:.0f}%"
    direction = "discount" if discount_pct < 0 else "premium"
    base = f"{season} R{round_} trading at {pct_label} {direction}"
    if trade_count:
        base += f" — {trade_count} recent trade{'s' if trade_count != 1 else ''}"
    if sig == "BUY":
        return f"{base}; consider acquiring before market corrects"
    if sig == "SELL":
        return f"{base}; move picks for players now"
    return f"{base}; fair value"


def analyze_pick_market(league_id: str = LEAGUE_ID) -> list[PickMarketSignal]:
    """Return pick market arbitrage signals for all known draft classes.

    Compares model-implied dynasty pick values against FantasyCalc market prices.
    Falls back to trade-frequency estimation when FantasyCalc is unavailable.
    Sorted by abs(discount_pct) descending.
    """
    # Fetch FC pick values first (external ground truth).
    try:
        from sleeper_ffm.market.blend import pick_market_values

        fc_picks = pick_market_values()
        log.info("analyze_pick_market: %d FC pick prices loaded", len(fc_picks))
    except Exception as exc:
        log.warning("analyze_pick_market: FC pick fetch failed (%s); using trade-frequency", exc)
        fc_picks = {}

    trade_counts: dict[tuple[str, int], int] = {}

    with SleeperClient(league_id=league_id) as client:
        for pick in client.traded_picks():
            key = (pick.season, pick.round)
            trade_counts[key] = trade_counts.get(key, 0) + 1

        # Supplement with picks traded within each draft
        try:
            drafts = client.league_drafts()
        except Exception as exc:
            log.warning("league_drafts() failed: %s", exc)
            drafts = []

        for draft in drafts:
            if not draft.season:
                continue
            try:
                for pick in client.draft_traded_picks(draft.draft_id):
                    key = (pick.season, pick.round)
                    trade_counts[key] = trade_counts.get(key, 0) + 1
            except Exception as exc:
                log.warning("draft_traded_picks(%s) failed: %s", draft.draft_id, exc)

    # Ensure future seasons are always represented even with zero trades
    observed_keys = set(trade_counts.keys())
    for season in _FUTURE_SEASONS:
        for round_ in _ALL_ROUNDS:
            observed_keys.add((season, round_))

    signals: list[PickMarketSignal] = []
    for season, round_ in observed_keys:
        if round_ not in _BASE:
            log.debug("Skipping unknown round %d", round_)
            continue

        count = trade_counts.get((season, round_), 0)
        mv = _model_value(season, round_)

        market = market_pick_value(season, round_)
        if market is not None:
            mkt = market
            source = "fantasycalc"
        else:
            mkt, source = _market_value_from_trades(mv, count)
            mkt = round(mkt, 2)

        disc = (mkt - mv) / mv if mv else 0.0
        sig = _signal(disc)
        rat = _rationale(season, round_, disc, count, sig)

        signals.append(
            PickMarketSignal(
                season=season,
                round=round_,
                model_value=round(mv, 2),
                market_value=mkt,
                discount_pct=round(disc, 4),
                signal=sig,
                rationale=rat,
                trade_count=count,
                market_source=source,
            )
        )

    signals.sort(key=lambda s: abs(s.discount_pct), reverse=True)
    return signals
