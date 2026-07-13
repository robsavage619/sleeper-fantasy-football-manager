from __future__ import annotations

from sleeper_ffm.act.plans import build_transaction_plan
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


def test_transaction_plan_is_non_mutating_and_confirm_gated() -> None:
    plan = build_transaction_plan(
        action_id="trade-offer-4",
        kind="trade",
        command="Offer Player A for Player B",
    )

    assert plan.status == "READY_FOR_MANUAL_CONFIRMATION"
    assert plan.confirm_phrase == "CONFIRM TRADE trade-offer-4"
    assert "does not submit Sleeper transactions" in plan.warnings[0]
