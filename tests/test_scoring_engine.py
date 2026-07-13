from __future__ import annotations

from sleeper_ffm.scoring.engine import _derive_bonuses, score, stats_from_nflverse

# This league's verified scoring (subset that these tests exercise).
SCORING = {
    "pass_yd": 0.04, "pass_td": 4.0, "pass_int": -1.0, "bonus_pass_yd_300": 2.5,
    "bonus_pass_yd_400": 5.0, "bonus_pass_cmp_25": 2.5,
    "rush_yd": 0.1, "rush_td": 6.0, "bonus_rush_yd_100": 2.5, "bonus_rush_yd_200": 5.0,
    "bonus_rush_att_20": 1.0,
    "rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0, "bonus_rec_yd_100": 2.5, "bonus_rec_yd_200": 5.0,
    "fum_lost": -1.0,
}


def test_ppr_receiving_line_no_bonus() -> None:
    # 6 rec, 84 yds, 1 TD: 6 + 8.4 + 6 = 20.4
    stats = {"rec": 6, "rec_yd": 84, "rec_td": 1}
    assert score(stats, SCORING) == 20.4


def test_receiving_100yd_bonus_fires() -> None:
    # 8 rec, 120 yds, 1 TD: 8 + 12 + 6 + 2.5(100-bonus) = 28.5
    stats = {"rec": 8, "rec_yd": 120, "rec_td": 1}
    assert score(stats, SCORING) == 28.5


def test_receiving_bonuses_stack_at_200() -> None:
    # 10 rec, 205 yds: 10 + 20.5 + 2.5(100) + 5(200) = 38.0
    stats = {"rec": 10, "rec_yd": 205}
    assert score(stats, SCORING) == 38.0


def test_qb_line_with_passing_bonuses() -> None:
    # 28/40, 415 yds, 3 TD, 1 INT, 30 rush yds:
    # pass_yd 415*.04=16.6, pass_td 12, int -1, rush 3,
    # bonuses: cmp>=25 2.5, pass 300 2.5, pass 400 5 => 40.6
    stats = {
        "pass_cmp": 28, "pass_yd": 415, "pass_td": 3, "pass_int": 1, "rush_yd": 30,
    }
    assert score(stats, SCORING) == 40.6


def test_rushing_att_and_yardage_bonuses() -> None:
    # 22 att, 140 yds, 2 TD: 14 + 12 + 2.5(100) + 1(20-att) = 29.5
    stats = {"rush_att": 22, "rush_yd": 140, "rush_td": 2}
    assert score(stats, SCORING) == 29.5


def test_fumble_penalty() -> None:
    stats = {"rec": 4, "rec_yd": 40, "fum_lost": 1}
    assert score(stats, SCORING) == 7.0


def test_supplied_length_td_bonus_not_overwritten() -> None:
    # Source (Sleeper) supplies a 40+ yd TD flag; engine must not zero it.
    stats = {"rec": 1, "rec_yd": 55, "rec_td": 1, "rec_td_40p": 1}
    scoring = {**SCORING, "rec_td_40p": 2.5}
    # 1 + 5.5 + 6 + 2.5 = 15.0
    assert score(stats, scoring) == 15.0


def test_derive_bonuses_idempotent() -> None:
    stats = {"rec_yd": 150.0}
    _derive_bonuses(stats)
    _derive_bonuses(stats)
    assert stats["bonus_rec_yd_100"] == 1.0
    assert stats["bonus_rec_yd_200"] == 0.0


def test_stats_from_nflverse_sums_fumbles_and_maps_columns() -> None:
    row = {
        "receptions": 5, "receiving_yards": 62, "receiving_tds": 1,
        "rushing_fumbles_lost": 1, "receiving_fumbles_lost": 1, "sack_fumbles_lost": 0,
        "carries": 3, "rushing_yards": 18,
    }
    stats = stats_from_nflverse(row)
    assert stats["rec"] == 5
    assert stats["fum_lost"] == 2
    assert stats["rush_yd"] == 18
