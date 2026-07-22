from __future__ import annotations

import pytest

from sleeper_ffm.evals import early_claim

_SLOTS = ["QB", "RB", "WR", "FLEX", "BN", "BN"]
_POS = {
    "qb1": "QB",
    "rb1": "RB",
    "rb2": "RB",
    "rb3": "RB",
    "wr1": "WR",
    "wr2": "WR",
    "te1": "TE",
}


def test_free_agent_pool_excludes_anyone_rostered() -> None:
    universe = frozenset({"a", "b", "c", "d"})
    pool = early_claim.free_agent_pool(universe, {"b", "d"})
    assert sorted(pool) == ["a", "c"]


def test_free_agent_pool_empty_when_universe_fully_rostered() -> None:
    universe = frozenset({"a", "b"})
    assert early_claim.free_agent_pool(universe, {"a", "b", "c"}) == []


def test_realized_points_prefers_sleeper_ground_truth() -> None:
    points_by_week = {5: {"a": 12.0}}
    nflverse = {("gA", 5): 99.0}  # would be wrong if used — sleeper's 12.0 must win
    out = early_claim.realized_points("a", 5, points_by_week, nflverse, {"a": "gA"})
    assert out == 12.0


def test_realized_points_falls_back_to_nflverse_when_never_rostered() -> None:
    out = early_claim.realized_points("a", 5, {}, {("gA", 5): 8.5}, {"a": "gA"})
    assert out == 8.5


def test_realized_points_zero_when_no_crosswalk_and_never_rostered() -> None:
    assert early_claim.realized_points("a", 5, {}, {("gA", 5): 8.5}, {}) == 0.0


def test_counterfactual_week_points_measures_the_swap_only() -> None:
    roster = ["qb1", "rb1", "rb2", "wr1", "te1"]
    projected = {"qb1": 20.0, "rb1": 15.0, "rb2": 5.0, "wr1": 12.0, "te1": 8.0, "pickup": 14.0}
    realized = {"qb1": 22.0, "rb1": 10.0, "rb2": 0.0, "wr1": 9.0, "te1": 6.0, "pickup": 30.0}
    baseline, mutated = early_claim.counterfactual_week_points(
        roster, "rb2", "pickup", _POS | {"pickup": "RB"}, _SLOTS, projected, realized
    )
    # baseline lineup: qb1, rb1, wr1, FLEX=te1(8>rb2's 5 projected) -> 22+10+9+6=47
    assert baseline == 47.0
    # mutated: rb2 dropped, pickup added and wins FLEX over te1 (14>8) -> qb1,rb1,wr1,pickup
    assert mutated == 22.0 + 10.0 + 9.0 + 30.0


def test_counterfactual_week_points_is_zero_diff_when_swap_never_starts() -> None:
    # pickup projects worse than everyone on the bench — never enters the lineup either way.
    roster = ["qb1", "rb1", "rb2", "wr1", "te1"]
    projected = {"qb1": 20.0, "rb1": 15.0, "rb2": 12.0, "wr1": 12.0, "te1": 8.0, "pickup": 0.5}
    realized = {"qb1": 20.0, "rb1": 15.0, "rb2": 12.0, "wr1": 12.0, "te1": 8.0, "pickup": 40.0}
    baseline, mutated = early_claim.counterfactual_week_points(
        roster, "te1", "pickup", _POS | {"pickup": "RB"}, _SLOTS, projected, realized
    )
    assert baseline == mutated  # projection never trusted the pickup enough to start him


def test_select_best_add_skips_a_candidate_that_cannot_crack_the_lineup() -> None:
    # A backup QB out-projects the worst bench RB by raw score, but the roster already
    # starts a much better QB — the QB swap changes nothing, so it must not be picked.
    roster = ["qb1", "rb1", "rb2", "wr1", "te1"]
    watchlist = ["backup_qb"]
    positions = _POS | {"backup_qb": "QB"}
    projected = {
        "qb1": 22.0,
        "rb1": 15.0,
        "rb2": 0.0,
        "wr1": 12.0,
        "te1": 8.0,
        "backup_qb": 16.0,  # beats rb2 on raw score, but can't unseat qb1
    }
    out = early_claim.select_best_add(watchlist, roster, "rb2", positions, _SLOTS, projected)
    assert out is None


def test_select_best_add_picks_a_flex_eligible_upgrade() -> None:
    roster = ["qb1", "rb1", "rb2", "wr1", "te1"]
    watchlist = ["backup_qb", "gem_wr"]
    positions = _POS | {"backup_qb": "QB", "gem_wr": "WR"}
    projected = {
        "qb1": 22.0,
        "rb1": 15.0,
        "rb2": 0.0,
        "wr1": 12.0,
        "te1": 8.0,
        "backup_qb": 16.0,  # cannot help — see above
        "gem_wr": 14.0,  # beats rb2 (FLEX-eligible swap) and improves the projected total
    }
    out = early_claim.select_best_add(watchlist, roster, "rb2", positions, _SLOTS, projected)
    assert out == "gem_wr"


def test_select_best_add_prefers_the_larger_projected_gain() -> None:
    roster = ["qb1", "rb1", "rb2", "wr1", "te1"]
    watchlist = ["small_gain", "big_gain"]
    positions = _POS | {"small_gain": "WR", "big_gain": "WR"}
    projected = {
        "qb1": 22.0,
        "rb1": 15.0,
        "rb2": 0.0,
        "wr1": 12.0,
        "te1": 8.0,
        "small_gain": 9.0,
        "big_gain": 20.0,
    }
    out = early_claim.select_best_add(watchlist, roster, "rb2", positions, _SLOTS, projected)
    assert out == "big_gain"


def test_random_anticipation_prob_grows_with_more_candidate_weeks() -> None:
    pool_sizes = {3: 100, 4: 100, 5: 100}
    p_one_week = early_claim.random_anticipation_prob(
        pool_sizes, min_week=3, claim_week=4, top_k=10
    )
    p_two_weeks = early_claim.random_anticipation_prob(
        pool_sizes, min_week=3, claim_week=5, top_k=10
    )
    assert 0.0 < p_one_week < p_two_weeks < 1.0
    assert p_one_week == pytest.approx(0.10)


def test_random_anticipation_prob_zero_with_no_prior_weeks() -> None:
    assert early_claim.random_anticipation_prob({3: 100}, min_week=3, claim_week=3, top_k=10) == 0.0


def test_random_anticipation_prob_caps_at_one_when_top_k_exceeds_pool() -> None:
    pool_sizes = {3: 5}
    p = early_claim.random_anticipation_prob(pool_sizes, min_week=3, claim_week=4, top_k=10)
    assert p == 1.0


def test_join_anticipation_flags_a_pre_claim_watchlist_hit() -> None:
    value_adds = [("gem", 8, 5, 42.0)]  # claimed week 8 by roster 5, worth 42 realized pts
    watchlist = {"gem": 6}  # engine flagged him at week 6 — 2 weeks of lead
    stolen, missed = early_claim.join_anticipation(value_adds, watchlist)
    assert missed == []
    assert len(stolen) == 1
    s = stolen[0]
    assert s.player_id == "gem" and s.claim_week == 8 and s.first_flagged_week == 6
    assert s.lead_weeks == 2 and s.realized_value == 42.0


def test_join_anticipation_same_week_flag_does_not_count() -> None:
    # Flagged the same week he was claimed — too late to act on, not anticipation.
    value_adds = [("gem", 8, 5, 42.0)]
    stolen, missed = early_claim.join_anticipation(value_adds, {"gem": 8})
    assert stolen == []
    assert len(missed) == 1 and missed[0].player_id == "gem"


def test_join_anticipation_never_flagged_is_missed() -> None:
    value_adds = [("ghost", 8, 5, 30.0)]
    stolen, missed = early_claim.join_anticipation(value_adds, {})
    assert stolen == []
    assert missed[0].player_id == "ghost" and missed[0].realized_value == 30.0


def test_join_anticipation_handles_multiple_value_adds() -> None:
    value_adds = [("a", 5, 1, 20.0), ("b", 6, 2, 15.0), ("c", 7, 3, 10.0)]
    watchlist = {"a": 3, "c": 7}  # a: anticipated; b: never flagged; c: flagged same week
    stolen, missed = early_claim.join_anticipation(value_adds, watchlist)
    assert {s.player_id for s in stolen} == {"a"}
    assert {m.player_id for m in missed} == {"b", "c"}
