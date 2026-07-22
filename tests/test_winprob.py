from __future__ import annotations

import pytest

from sleeper_ffm.evals import winprob
from sleeper_ffm.evals.arena import PointHistory, select_lineup

_SLOTS = ["QB", "RB", "WR", "FLEX", "BN", "BN"]
_POS = {
    "qb1": "QB",
    "rb1": "RB",
    "rb2": "RB",
    "wr1": "WR",
    "wr2": "WR",
    "te1": "TE",
}


def test_win_probability_is_monotone_and_bounded() -> None:
    assert winprob.win_probability(100, 400, 100, 400) == pytest.approx(0.5)
    assert winprob.win_probability(120, 400, 100, 400) > 0.5
    assert winprob.win_probability(80, 400, 100, 400) < 0.5
    # Degenerate zero-variance case falls back to a mean comparison.
    assert winprob.win_probability(101, 0, 100, 0) == 1.0
    assert winprob.win_probability(99, 0, 100, 0) == 0.0


def test_underdog_gains_from_more_variance_favorite_loses() -> None:
    # Same means; only my variance changes.
    p_low, p_high = (winprob.win_probability(90, v, 100, 400) for v in (100, 900))
    assert p_high > p_low  # underdog wants variance
    p_low, p_high = (winprob.win_probability(110, v, 100, 400) for v in (100, 900))
    assert p_high < p_low  # favorite wants the floor


def test_assign_lineup_matches_select_lineup_choices() -> None:
    means = {"qb1": 20.0, "rb1": 15.0, "rb2": 12.0, "wr1": 10.0, "wr2": 6.0, "te1": 8.0}
    assignment = winprob.assign_lineup(means, _POS, _SLOTS)
    assert {pid for _, pid in assignment} == set(select_lineup(means, _POS, _SLOTS))
    slots = [slot for slot, _ in assignment]
    assert slots.count("FLEX") == 1


def _stds(means: dict[str, float], cv_by_pos: dict[str, float]) -> dict[str, float]:
    return {pid: cv_by_pos[_POS[pid]] * mean for pid, mean in means.items()}


def test_winprob_selector_keeps_mean_lineup_when_a_clear_favorite() -> None:
    means = {"qb1": 25.0, "rb1": 20.0, "rb2": 5.0, "wr1": 15.0, "wr2": 5.0, "te1": 14.0}
    stds = _stds(means, dict.fromkeys(winprob._DEFAULT_CVS, 0.5))
    ids, p = winprob.select_winprob_lineup(means, stds, _POS, _SLOTS, 30.0, 400.0)
    assert set(ids) == set(select_lineup(means, _POS, _SLOTS))
    assert p > 0.9


def test_winprob_selector_takes_a_variance_swap_as_a_big_underdog() -> None:
    # wr2 projects 2.5 points under te1 but is far more volatile. Against a much stronger
    # opponent the selector should FLEX the boom-bust player.
    means = {"qb1": 20.0, "rb1": 15.0, "rb2": 10.0, "wr1": 12.0, "wr2": 8.0, "te1": 10.5}
    stds = _stds(means, {"QB": 0.3, "RB": 0.3, "WR": 1.4, "TE": 0.1})
    mean_ids = select_lineup(means, _POS, _SLOTS)
    assert "te1" in mean_ids and "wr2" not in mean_ids
    ids, _p = winprob.select_winprob_lineup(means, stds, _POS, _SLOTS, 90.0, 100.0)
    assert "wr2" in ids and "te1" not in ids  # variance-seeking FLEX swap


def test_winprob_selector_swaps_within_a_position_on_player_level_variance() -> None:
    # Same position, near-equal means: steady wr1 starts, boom-bust wr2 sits (FLEX goes
    # to rb2). As a heavy underdog the selector should swap the WR slot to the volatile
    # player — the swap position-pooled CVs can never see.
    means = {"qb1": 20.0, "rb1": 15.0, "rb2": 13.0, "wr1": 12.0, "wr2": 11.0, "te1": 6.0}
    stds = {"qb1": 6.0, "rb1": 4.5, "rb2": 3.5, "wr1": 2.0, "wr2": 14.0, "te1": 2.0}
    mean_ids = select_lineup(means, _POS, _SLOTS)
    assert "wr1" in mean_ids and "wr2" not in mean_ids
    ids, _p = winprob.select_winprob_lineup(means, stds, _POS, _SLOTS, 90.0, 100.0)
    assert "wr2" in ids  # the boom-bust wideout gets the start as an underdog


def test_winprob_selector_respects_the_sacrifice_cap() -> None:
    # wr2 is high-variance but 10+ projected points worse — never a legal swap.
    means = {"qb1": 20.0, "rb1": 15.0, "rb2": 10.0, "wr1": 12.0, "wr2": 0.5, "te1": 10.5}
    stds = _stds(means, {"QB": 0.3, "RB": 0.3, "WR": 2.0, "TE": 0.1})
    stds["wr2"] = 20.0
    ids, _p = winprob.select_winprob_lineup(means, stds, _POS, _SLOTS, 200.0, 100.0)
    assert "wr2" not in ids


def test_winprob_selector_only_swaps_legal_positions_into_dedicated_slots() -> None:
    # The only QB stays even if a volatile WR would add variance — WRs can't fill QB.
    means = {"qb1": 10.0, "rb1": 15.0, "rb2": 12.0, "wr1": 12.0, "wr2": 9.0, "te1": 8.0}
    stds = _stds(means, {"QB": 0.1, "RB": 0.4, "WR": 1.5, "TE": 0.4})
    ids, _p = winprob.select_winprob_lineup(means, stds, _POS, _SLOTS, 150.0, 100.0)
    assert "qb1" in ids


def test_player_stds_shrink_toward_position_and_separate_boom_bust() -> None:
    hist = PointHistory(
        {
            "wr1": [12.0, 12.0, 12.0, 12.0, 12.0, 12.0],  # metronome
            "wr2": [30.0, 0.0, 25.0, 0.0, 20.0, 0.0],  # boom-bust
        }
    )
    means = {"wr1": 12.0, "wr2": 12.0}
    stds = winprob.player_stds(means, hist, {"wr1": "WR", "wr2": "WR"}, {"WR": 0.75})
    assert stds["wr2"] > stds["wr1"]  # same mean, very different risk
    assert stds["wr1"] > 0.0  # shrinkage keeps the steady player off zero
    # A player with no history projects at the position CV exactly.
    stds_new = winprob.player_stds({"wr3": 10.0}, hist, {"wr3": "WR"}, {"WR": 0.75})
    assert stds_new["wr3"] == pytest.approx(7.5)


def test_position_cvs_measures_history_and_falls_back_when_thin() -> None:
    hist = PointHistory(
        {
            "rb1": [10.0, 10.0, 10.0, 10.0],  # rock steady
            "rb2": [20.0, 0.0, 20.0, 0.0],  # boom-bust
            "rb3": [5.0, 15.0, 10.0, 10.0],
            "wr1": [8.0],  # too few games
        }
    )
    pos = {"rb1": "RB", "rb2": "RB", "rb3": "RB", "wr1": "WR"}
    cvs = winprob.position_cvs(hist, pos)
    assert cvs["RB"] != winprob._DEFAULT_CVS["RB"]  # measured, not default
    assert cvs["WR"] == winprob._DEFAULT_CVS["WR"]  # thin sample -> fallback
    assert 0.0 < cvs["RB"] < 1.5


def test_calibration_buckets_partition_predictions() -> None:
    preds = [(0.1, False), (0.15, False), (0.5, True), (0.55, False), (0.9, True)]
    rows = winprob._calibration_buckets(preds, width=0.2)
    assert sum(n for _, _, n in rows) == len(preds)
    assert rows[0] == (0.0, 0.0, 2)
