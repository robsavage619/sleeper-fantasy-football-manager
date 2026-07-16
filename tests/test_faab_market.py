"""Tests for the FAAB clearing-price model (pure helpers — no network)."""

from __future__ import annotations

from sleeper_ffm.model.faab_market import (
    FaabMarket,
    WaiverBid,
    build_bid_history,
    predicted_clearing_price,
    recommended_bid,
)


def _bid(position: str, bid: int, roster_id: int = 1) -> WaiverBid:
    return WaiverBid(
        season="2025", week=1, roster_id=roster_id, player_id="p", position=position, bid=bid
    )


def test_build_bid_history_position_percentiles() -> None:
    bids = [_bid("RB", v) for v in [10, 20, 30, 40, 50]]
    by_position, _ = build_bid_history(bids)
    stats = by_position["RB"]
    assert stats.n == 5
    assert stats.p50 == 30.0
    assert stats.p25 is not None and stats.p90 is not None
    assert stats.p25 < stats.p50 < stats.p90


def test_build_bid_history_below_min_sample_has_none_percentiles() -> None:
    bids = [_bid("TE", 10), _bid("TE", 20)]
    by_position, _ = build_bid_history(bids)
    stats = by_position["TE"]
    assert stats.n == 2
    assert stats.p25 is None
    assert stats.p50 is None


def test_owner_profile_aggressiveness_labels() -> None:
    bids = [
        _bid("RB", 5, roster_id=1),
        _bid("WR", 6, roster_id=1),
        _bid("RB", 4, roster_id=1),  # conservative bidder
        _bid("RB", 90, roster_id=2),
        _bid("WR", 95, roster_id=2),
        _bid("RB", 88, roster_id=2),  # aggressive bidder
        _bid("RB", 20, roster_id=3),
        _bid("WR", 22, roster_id=3),
        _bid("RB", 18, roster_id=3),  # typical bidder
    ]
    _, by_owner = build_bid_history(bids)
    assert by_owner[1].aggressiveness == "CONSERVATIVE"
    assert by_owner[2].aggressiveness == "AGGRESSIVE"
    assert by_owner[3].aggressiveness == "TYPICAL"


def test_owner_profile_unknown_below_min_bids() -> None:
    bids = [_bid("RB", 10, roster_id=9), _bid("RB", 15, roster_id=9)]
    _, by_owner = build_bid_history(bids)
    assert by_owner[9].aggressiveness == "UNKNOWN"
    assert by_owner[9].median_bid is None


def test_predicted_clearing_price_maps_priority_to_percentile() -> None:
    bids = [_bid("WR", v) for v in [5, 10, 15, 20, 25, 60, 65, 70, 80, 100]]
    by_position, by_owner = build_bid_history(bids)
    market = FaabMarket(
        seasons_covered=["2025"], bids=bids, by_position=by_position, by_owner=by_owner
    )

    high = predicted_clearing_price("WR", 85.0, market)
    mid = predicted_clearing_price("WR", 50.0, market)
    low = predicted_clearing_price("WR", 10.0, market)
    assert high is not None and mid is not None and low is not None
    assert low < mid < high


def test_predicted_clearing_price_none_when_position_unseen() -> None:
    market = FaabMarket(seasons_covered=[], bids=[], by_position={}, by_owner={})
    assert predicted_clearing_price("QB", 90.0, market) is None


def test_recommended_bid_is_clearing_price_plus_one_capped_at_budget() -> None:
    bids = [_bid("RB", v) for v in [10, 20, 30, 40, 50]]
    by_position, by_owner = build_bid_history(bids)
    market = FaabMarket(
        seasons_covered=["2025"], bids=bids, by_position=by_position, by_owner=by_owner
    )

    bid = recommended_bid("RB", 50.0, market, budget_remaining=500)
    price = predicted_clearing_price("RB", 50.0, market)
    assert price is not None
    assert bid == price + 1

    capped = recommended_bid("RB", 90.0, market, budget_remaining=5)
    assert capped == 5


def test_recommended_bid_none_when_no_clearing_price() -> None:
    market = FaabMarket(seasons_covered=[], bids=[], by_position={}, by_owner={})
    assert recommended_bid("QB", 50.0, market, budget_remaining=100) is None
