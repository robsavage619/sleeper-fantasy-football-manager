from __future__ import annotations

import pytest

from sleeper_ffm.model import elo


def test_equal_teams_are_a_cointoss() -> None:
    assert elo.expected_score(1500.0, 1500.0) == pytest.approx(0.5)


def test_a_400_point_edge_is_ten_to_one() -> None:
    assert elo.expected_score(1900.0, 1500.0) == pytest.approx(10 / 11, abs=1e-6)


def test_expected_scores_are_complementary() -> None:
    a = elo.expected_score(1620.0, 1480.0)
    b = elo.expected_score(1480.0, 1620.0)
    assert a + b == pytest.approx(1.0)


def test_bigger_margins_move_the_rating_more() -> None:
    close = elo.mov_multiplier(3.0, 0.0)
    blowout = elo.mov_multiplier(28.0, 0.0)
    assert blowout > close > 0


def test_autocorrelation_damps_a_favorite_blowout() -> None:
    """The same margin counts less when the winner was already far ahead on Elo."""
    underdog_wins_big = elo.mov_multiplier(21.0, -200.0)
    favorite_wins_big = elo.mov_multiplier(21.0, 200.0)
    assert underdog_wins_big > favorite_wins_big


def test_update_is_zero_sum() -> None:
    p = elo.EloParams()
    home, away = elo.update_pair(1500.0, 1500.0, 30.0, 10.0, p)
    assert (home - 1500.0) == pytest.approx(1500.0 - away)


def test_winner_gains_and_loser_loses() -> None:
    p = elo.EloParams()
    home, away = elo.update_pair(1500.0, 1500.0, 24.0, 20.0, p)
    assert home > 1500.0 > away


def test_beating_a_much_weaker_team_barely_moves_you() -> None:
    p = elo.EloParams()
    strong_wins, _ = elo.update_pair(1800.0, 1300.0, 27.0, 10.0, p)
    upset_home, _ = elo.update_pair(1300.0, 1800.0, 27.0, 10.0, p)
    assert (strong_wins - 1800.0) < (upset_home - 1300.0)


def test_home_advantage_raises_the_home_win_probability() -> None:
    p = elo.EloParams(home_advantage=48.0)
    with_hfa = elo.expected_score(1500.0 + p.home_advantage, 1500.0)
    neutral = elo.expected_score(1500.0, 1500.0)
    assert with_hfa > neutral


def test_neutral_site_zeroes_home_advantage() -> None:
    p = elo.EloParams(home_advantage=48.0)
    home_h, _ = elo.update_pair(1500.0, 1500.0, 21.0, 20.0, p, neutral=False)
    home_n, _ = elo.update_pair(1500.0, 1500.0, 21.0, 20.0, p, neutral=True)
    # At a neutral site the home team was less expected to win, so the same narrow win
    # is worth more Elo.
    assert home_n > home_h


def test_a_tie_moves_both_toward_each_other() -> None:
    p = elo.EloParams()
    home, away = elo.update_pair(1600.0, 1400.0, 17.0, 17.0, p, neutral=True)
    assert home < 1600.0 and away > 1400.0  # favorite drops, underdog rises


def test_season_regression_pulls_toward_the_mean() -> None:
    p = elo.EloParams(season_regression=1 / 3, mean=1505.0)
    hot = elo._regress_to_mean(1700.0, p)
    cold = elo._regress_to_mean(1300.0, p)
    assert hot == pytest.approx(1700.0 - (1700.0 - 1505.0) / 3)
    assert cold == pytest.approx(1300.0 + (1505.0 - 1300.0) / 3)


def test_board_falls_back_to_league_mean_for_unknown_teams() -> None:
    board = elo.EloBoard(ratings=[elo.TeamRating("KC", 1690.0, 200, 2024, 22)])
    assert board.rating("KC") == 1690.0
    assert board.rating("XXX") == board.params.mean


def test_board_win_probability_uses_home_advantage() -> None:
    board = elo.EloBoard(
        ratings=[
            elo.TeamRating("KC", 1600.0, 1, 2024, 1),
            elo.TeamRating("DEN", 1600.0, 1, 2024, 1),
        ]
    )
    assert board.win_probability("KC", "DEN") > 0.5
    assert board.win_probability("KC", "DEN", neutral=True) == pytest.approx(0.5)


# --- QB adjustment ------------------------------------------------------------------


def test_qb_value_rewards_a_clean_game_and_punishes_a_bad_one() -> None:
    clean = elo.qb_game_value(
        {
            "attempts": 30,
            "completions": 22,
            "passing_yards": 300,
            "passing_tds": 3,
            "interceptions": 0,
            "sacks_suffered": 1,
            "rushing_yards": 20,
        }
    )
    ugly = elo.qb_game_value(
        {
            "attempts": 35,
            "completions": 15,
            "passing_yards": 140,
            "passing_tds": 0,
            "interceptions": 4,
            "sacks_suffered": 6,
        }
    )
    assert clean > ugly
    assert ugly < 0  # a 4-INT, 6-sack line is genuinely negative value


def test_qb_value_ignores_missing_keys() -> None:
    assert elo.qb_game_value({}) == 0.0
    assert elo.qb_game_value({"passing_tds": 2}) == pytest.approx(22.6)


def test_qb_adjustment_raises_for_above_baseline_starter() -> None:
    p = elo.EloParams(qb_value_per_elo=3.3)
    better = elo._qb_adjustment(qb_val=120.0, team_baseline=60.0, params=p)
    worse = elo._qb_adjustment(qb_val=20.0, team_baseline=60.0, params=p)
    assert better > 0 > worse
    assert elo._qb_adjustment(None, 60.0, p) == 0.0  # unknown QB → no adjustment


def test_moneyline_prob_is_devigged_and_favors_the_minus_side() -> None:
    prob = elo._moneyline_prob({"home_moneyline": -200, "away_moneyline": +170})
    assert prob is not None and prob > 0.5
    assert elo._moneyline_prob({"home_moneyline": None, "away_moneyline": 100}) is None


def test_devig_normalizes_to_one() -> None:
    row = {"home_moneyline": -150, "away_moneyline": +130}
    home = elo._moneyline_prob(row)
    away = elo._moneyline_prob({"home_moneyline": 130, "away_moneyline": -150})
    assert home is not None and away is not None
    assert home + away == pytest.approx(1.0, abs=1e-3)


def test_american_to_prob_endpoints() -> None:
    assert elo._american_to_prob(-100) == pytest.approx(0.5)
    assert elo._american_to_prob(100) == pytest.approx(0.5)
    assert elo._american_to_prob(-300) == pytest.approx(0.75)
