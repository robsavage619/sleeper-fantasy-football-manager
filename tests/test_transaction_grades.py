from __future__ import annotations

from dataclasses import dataclass

from sleeper_ffm.model import transaction_grades as tg


@dataclass
class _Bid:
    """Minimal stand-in for faab_market.WaiverBid — only fields bid_percentile reads."""

    position: str
    bid: int


# --- bid_percentile --------------------------------------------------------------------


def test_bid_percentile_none_when_position_sample_too_thin() -> None:
    bids = [_Bid("WR", 10), _Bid("WR", 20)]
    assert tg.bid_percentile("WR", 15, bids) is None


def test_bid_percentile_computes_fraction_at_or_below() -> None:
    bids = [_Bid("WR", b) for b in (5, 10, 15, 20, 25)]
    # 3 of 5 bids <= 15
    assert tg.bid_percentile("WR", 15, bids) == 0.6


def test_bid_percentile_ignores_other_positions() -> None:
    bids = [_Bid("WR", 5), _Bid("WR", 10), _Bid("WR", 15), _Bid("RB", 1), _Bid("RB", 1)]
    # only WR bids count toward the WR sample; RB noise must not lower the threshold
    assert tg.bid_percentile("WR", 10, bids) is None  # only 3 WR bids, below the min of 5


def test_bid_percentile_a_zero_bid_beats_everything() -> None:
    bids = [_Bid("RB", b) for b in (5, 10, 15, 20, 25)]
    assert tg.bid_percentile("RB", 0, bids) == 0.0


# --- league_points_per_dollar / claim_surplus -------------------------------------------


def test_league_points_per_dollar_zero_when_no_spend() -> None:
    assert tg.league_points_per_dollar([0, 0], [50.0, 30.0]) == 0.0


def test_league_points_per_dollar_computes_the_rate() -> None:
    assert tg.league_points_per_dollar([10, 10], [100.0, 50.0]) == 7.5


def test_claim_surplus_zero_bid_keeps_full_realized_total() -> None:
    assert tg.claim_surplus(42.0, 0, league_rate=5.0) == 42.0


def test_claim_surplus_penalizes_expensive_busts() -> None:
    # paid $20 at a 5 pt/$ rate (expected 100), only returned 10 -> deep negative surplus.
    assert tg.claim_surplus(10.0, 20, league_rate=5.0) == -90.0


def test_claim_surplus_rewards_cheap_steals() -> None:
    assert tg.claim_surplus(80.0, 5, league_rate=5.0) == 55.0


# --- grade_on_curve / letter_gpa ---------------------------------------------------------


def test_grade_on_curve_best_value_gets_top_letter() -> None:
    letters = tg.grade_on_curve({0: 100.0, 1: 50.0, 2: 0.0})
    assert letters[0] == "A+"
    assert letters[2] == "D"


def test_grade_on_curve_single_entry_is_a_plus() -> None:
    assert tg.grade_on_curve({0: -999.0}) == {0: "A+"}


def test_letter_gpa_of_all_a_plus_is_top_of_scale() -> None:
    assert tg.letter_gpa(["A+", "A+"]) == 4.3


def test_letter_gpa_empty_is_zero() -> None:
    assert tg.letter_gpa([]) == 0.0


def test_letter_gpa_averages_mixed_grades() -> None:
    assert tg.letter_gpa(["A+", "D"]) == round((4.3 + 1.0) / 2, 2)


# --- is_settling -------------------------------------------------------------------------


def test_is_settling_false_for_a_past_season() -> None:
    assert tg.is_settling("2023", week=15, current_season="2024", current_week=3) is False


def test_is_settling_true_within_the_window() -> None:
    assert tg.is_settling("2024", week=2, current_season="2024", current_week=4) is True


def test_is_settling_false_once_enough_weeks_have_passed() -> None:
    assert tg.is_settling("2024", week=1, current_season="2024", current_week=5) is False


# --- assemble_waiver_grades / assemble_trade_grades (fixture-driven) --------------------


def _waiver_obs(
    season: str = "2024",
    week: int = 5,
    roster_id: int = 1,
    owner_name: str = "Rob",
    player_id: str = "p1",
    player_name: str = "Some Guy",
    position: str = "WR",
    bid: int = 10,
    realized_points: float = 50.0,
    startable_weeks: int = 3,
) -> tg._WaiverObservation:
    return tg._WaiverObservation(
        season=season,
        week=week,
        roster_id=roster_id,
        owner_name=owner_name,
        player_id=player_id,
        player_name=player_name,
        position=position,
        bid=bid,
        realized_points=realized_points,
        startable_weeks=startable_weeks,
    )


def test_assemble_waiver_grades_empty_input() -> None:
    assert tg.assemble_waiver_grades([], [], "2024", 10) == []


def test_assemble_waiver_grades_ranks_within_the_season() -> None:
    obs = [
        _waiver_obs(player_id="steal", bid=1, realized_points=80.0),
        _waiver_obs(player_id="bust", bid=40, realized_points=5.0),
    ]
    out = tg.assemble_waiver_grades(obs, [], current_season="2023", current_week=0)
    by_pid = {g.player_id: g for g in out}
    assert by_pid["steal"].grade == "A+"
    assert by_pid["bust"].grade == "D"
    assert by_pid["steal"].surplus > by_pid["bust"].surplus


def test_assemble_waiver_grades_flags_settling_moves() -> None:
    obs = [_waiver_obs(season="2024", week=15)]
    out = tg.assemble_waiver_grades(obs, [], current_season="2024", current_week=16)
    assert out[0].settling is True

    out2 = tg.assemble_waiver_grades(obs, [], current_season="2024", current_week=20)
    assert out2[0].settling is False


def _trade_obs(
    season: str = "2024",
    week: int = 6,
    roster_id: int = 1,
    owner_name: str = "Rob",
    partner_roster_id: int = 2,
    partner_name: str = "Rival",
    received: list[dict] | None = None,
    sent: list[dict] | None = None,
    picks_received: int = 0,
    picks_sent: int = 0,
    net_points: float = 30.0,
    dynasty_delta: float | None = None,
) -> tg._TradeObservation:
    return tg._TradeObservation(
        season=season,
        week=week,
        roster_id=roster_id,
        owner_name=owner_name,
        partner_roster_id=partner_roster_id,
        partner_name=partner_name,
        received=received
        if received is not None
        else [{"player_id": "a", "name": "A", "points": 40.0}],
        sent=sent if sent is not None else [{"player_id": "b", "name": "B", "points": 10.0}],
        picks_received=picks_received,
        picks_sent=picks_sent,
        net_points=net_points,
        dynasty_delta=dynasty_delta,
    )


def test_assemble_trade_grades_empty_input() -> None:
    assert tg.assemble_trade_grades([], "2024", 10) == []


def test_assemble_trade_grades_ranks_by_net_points() -> None:
    obs = [
        _trade_obs(roster_id=1, net_points=50.0),
        _trade_obs(roster_id=2, net_points=-20.0),
    ]
    out = tg.assemble_trade_grades(obs, current_season="2023", current_week=0)
    by_rid = {g.roster_id: g for g in out}
    assert by_rid[1].grade == "A+"
    assert by_rid[2].grade == "D"


def test_assemble_trade_grades_preserves_dynasty_delta_annotation() -> None:
    obs = [_trade_obs(dynasty_delta=250.0)]
    out = tg.assemble_trade_grades(obs, "2023", 0)
    assert out[0].dynasty_delta == 250.0


# --- build_gpa_table -----------------------------------------------------------------------


def test_build_gpa_table_ranks_managers_best_first() -> None:
    waiver = [
        tg.WaiverGrade(
            season="2024",
            week=1,
            roster_id=1,
            owner_name="Rob",
            player_id="p",
            player_name="P",
            position="WR",
            bid=0,
            bid_percentile=None,
            realized_points=10.0,
            startable_weeks=1,
            surplus=10.0,
            grade="A+",
            settling=False,
        ),
        tg.WaiverGrade(
            season="2024",
            week=1,
            roster_id=2,
            owner_name="Rival",
            player_id="q",
            player_name="Q",
            position="WR",
            bid=0,
            bid_percentile=None,
            realized_points=0.0,
            startable_weeks=0,
            surplus=0.0,
            grade="D",
            settling=False,
        ),
    ]
    table = tg.build_gpa_table(waiver, [])
    assert [o.roster_id for o in table] == [1, 2]
    assert table[0].gpa == 4.3
    assert table[0].n_moves == 1
    assert "P" in table[0].best_move


def test_build_gpa_table_combines_waiver_and_trade_moves_per_owner() -> None:
    waiver = [
        tg.WaiverGrade(
            season="2024",
            week=1,
            roster_id=1,
            owner_name="Rob",
            player_id="p",
            player_name="P",
            position="WR",
            bid=0,
            bid_percentile=None,
            realized_points=10.0,
            startable_weeks=1,
            surplus=10.0,
            grade="A+",
            settling=False,
        )
    ]
    trade = tg.assemble_trade_grades(
        [_trade_obs(roster_id=1, net_points=-500.0)], current_season="2023", current_week=0
    )
    table = tg.build_gpa_table(waiver, trade)
    assert table[0].n_moves == 2
    assert table[0].worst_move.startswith("trade")


def test_build_gpa_table_empty_when_nothing_graded() -> None:
    assert tg.build_gpa_table([], []) == []
