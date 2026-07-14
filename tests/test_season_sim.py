"""Tests for the Monte-Carlo season simulator (pure, seeded core — no network)."""

from __future__ import annotations

from sleeper_ffm.model.season_sim import (
    _lineup_strength,
    round_robin_schedule,
    simulate,
)


def test_round_robin_is_balanced() -> None:
    fixtures = round_robin_schedule([1, 2, 3, 4], weeks=3)
    # 4 teams, 2 games per week, 3 weeks = 6 fixtures; everyone plays every week.
    assert len(fixtures) == 6
    for wk in (1, 2, 3):
        teams_this_week = [t for w, h, a in fixtures if w == wk for t in (h, a)]
        assert sorted(teams_this_week) == [1, 2, 3, 4]


def test_round_robin_handles_odd_teams_with_bye() -> None:
    fixtures = round_robin_schedule([1, 2, 3], weeks=3)
    # 3 teams → 1 game per week (one team byes), never the sentinel -1.
    assert all(h != -1 and a != -1 for _w, h, a in fixtures)
    assert len(fixtures) == 3


def test_stronger_team_wins_more_titles() -> None:
    strength = {1: 140.0, 2: 100.0, 3: 100.0, 4: 100.0}
    sched = round_robin_schedule([1, 2, 3, 4], weeks=12)
    odds = simulate(strength, sched, playoff_teams=2, std={t: 10.0 for t in strength}, n_sims=1000)
    assert odds[1]["title"] > odds[2]["title"]
    assert odds[1]["playoff"] > 0.9  # dominant team almost always makes a 2-team field


def test_odds_are_deterministic_under_seed() -> None:
    strength = {1: 120.0, 2: 110.0, 3: 100.0, 4: 90.0}
    sched = round_robin_schedule([1, 2, 3, 4], weeks=10)
    a = simulate(strength, sched, playoff_teams=2, n_sims=300, seed=42)
    b = simulate(strength, sched, playoff_teams=2, n_sims=300, seed=42)
    assert a == b


def test_title_odds_sum_to_one() -> None:
    strength = {1: 120.0, 2: 110.0, 3: 100.0, 4: 90.0, 5: 95.0, 6: 105.0}
    sched = round_robin_schedule(list(strength), weeks=10)
    odds = simulate(strength, sched, playoff_teams=4, n_sims=500)
    assert abs(sum(o["title"] for o in odds.values()) - 1.0) < 1e-9


def test_lineup_strength_picks_best_legal_lineup() -> None:
    # QB 20; RBs 15,12,4; WRs 18,14,10,3; TE 9. Best: QB20 + RB15,12 + WR18,14,10 + TE9
    # + 2 FLEX from leftovers {RB4, WR3} -> 4+3.
    per_game = {
        "q": ("QB", 20.0),
        "r1": ("RB", 15.0),
        "r2": ("RB", 12.0),
        "r3": ("RB", 4.0),
        "w1": ("WR", 18.0),
        "w2": ("WR", 14.0),
        "w3": ("WR", 10.0),
        "w4": ("WR", 3.0),
        "t1": ("TE", 9.0),
    }
    assert _lineup_strength(per_game) == 20 + 15 + 12 + 18 + 14 + 10 + 9 + 4 + 3
