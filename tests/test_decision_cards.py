from __future__ import annotations

from sleeper_ffm.act.plans import build_transaction_plan
from sleeper_ffm.model.faab_market import FaabMarket, PositionBidStats
from sleeper_ffm.season.waivers import analyze_waivers
from sleeper_ffm.sleeper.models import TrendingPlayer


def test_waiver_candidate_includes_decision_card_fields() -> None:
    players = {
        "add": {
            "position": "RB",
            "age": 22,
            "full_name": "Upside Back",
            "team": "FA",
        },
        "drop": {
            "position": "RB",
            "age": 29,
            "full_name": "Bench Clog",
            "search_rank": 999,
        },
    }

    candidates = analyze_waivers(
        sleeper_players=players,
        trending_adds=[TrendingPlayer(player_id="add", count=1000)],
        trending_drops=[],
        rostered_ids={"drop"},
        my_roster_ids={"drop"},
        protected_ids=set(),
    )

    assert candidates[0].drop_candidate == "Bench Clog"
    assert candidates[0].bid_min <= candidates[0].faab_estimate <= candidates[0].bid_max
    assert candidates[0].urgency in {"LOW", "MED", "HIGH"}
    assert candidates[0].decision


def test_waiver_candidate_uses_faab_market_when_available() -> None:
    players = {
        "add": {"position": "RB", "age": 22, "full_name": "Upside Back", "team": "FA"},
    }
    market = FaabMarket(
        seasons_covered=["2025"],
        bids=[],
        by_position={
            "RB": PositionBidStats(position="RB", n=10, p25=5.0, p50=15.0, p75=40.0, p90=90.0)
        },
        by_owner={},
    )

    candidates = analyze_waivers(
        sleeper_players=players,
        trending_adds=[TrendingPlayer(player_id="add", count=1000)],
        trending_drops=[],
        rostered_ids=set(),
        faab_market=market,
    )

    # Priority is capped at 100 for this trend volume -> p90 tier -> 90 + 1.
    assert candidates[0].faab_estimate == 91


def test_waiver_priority_rewards_roster_hole_over_surplus_at_same_position() -> None:
    """Identical trend/position/age signal, different roster context -> the hole ranks higher."""
    players_hole = {
        "wr_add": {"position": "WR", "age": 26, "full_name": "Available WR", "team": "FA"},
        "my_qb": {"position": "QB", "age": 27, "full_name": "My QB"},
    }
    players_surplus = {
        "wr_add": {"position": "WR", "age": 26, "full_name": "Available WR", "team": "FA"},
        "wr1": {"position": "WR", "age": 25, "full_name": "WR One"},
        "wr2": {"position": "WR", "age": 25, "full_name": "WR Two"},
        "wr3": {"position": "WR", "age": 25, "full_name": "WR Three"},
        "wr4": {"position": "WR", "age": 25, "full_name": "WR Four"},
    }
    trending = [TrendingPlayer(player_id="wr_add", count=1000)]

    no_context = analyze_waivers(
        sleeper_players=players_hole,
        trending_adds=trending,
        trending_drops=[],
        rostered_ids=set(),
    )[0]
    # Non-empty my_roster_ids with zero WRs on it -> a genuine hole at WR.
    hole = analyze_waivers(
        sleeper_players=players_hole,
        trending_adds=trending,
        trending_drops=[],
        rostered_ids={"my_qb"},
        my_roster_ids={"my_qb"},
    )[0]
    surplus = analyze_waivers(
        sleeper_players=players_surplus,
        trending_adds=trending,
        trending_drops=[],
        rostered_ids={"wr1", "wr2", "wr3", "wr4"},
        my_roster_ids={"wr1", "wr2", "wr3", "wr4"},
    )[0]

    # No roster context given at all -> no adjustment (an empty my_roster_ids means
    # "no signal," not "confirmed empty roster").
    assert no_context.add_priority == round(min(100.0, 50.0 + 5.0 + 20.0 + 4.0), 1)
    assert "roster hole" not in no_context.rationale
    # 0 rostered WRs (a real hole) outranks 4 already-rostered WRs (surplus) for
    # the identical trend/age signal.
    assert hole.add_priority > surplus.add_priority
    assert "roster hole" in hole.rationale
    assert "already deep" in surplus.rationale


def test_transaction_plan_is_non_mutating_and_confirm_gated() -> None:
    plan = build_transaction_plan(
        action_id="trade-offer-4",
        kind="trade",
        command="Offer Player A for Player B",
    )

    assert plan.status == "READY_FOR_MANUAL_CONFIRMATION"
    assert plan.confirm_phrase == "CONFIRM TRADE trade-offer-4"
    assert "does not submit Sleeper transactions" in plan.warnings[0]
