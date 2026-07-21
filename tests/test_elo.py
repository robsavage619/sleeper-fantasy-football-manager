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
