from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from sleeper_ffm.model import forecast as fc

_SCORING = {
    "rush_yd": 0.1,
    "rush_td": 6.0,
    "rec": 1.0,
    "rec_yd": 0.1,
    "rec_td": 6.0,
    "bonus_rush_yd_100": 3.0,
}


# --- recency weighting --------------------------------------------------------------


def test_exponential_weights_halve_at_the_half_life() -> None:
    w = fc.exponential_weights(5, half_life=4.0)
    assert w[-1] == pytest.approx(1.0)
    assert w[0] == pytest.approx(0.5)  # 4 games back
    assert all(a < b for a, b in pairwise(w))


def test_exponential_weights_edge_cases() -> None:
    assert fc.exponential_weights(0) == []
    with pytest.raises(ValueError, match="half_life"):
        fc.exponential_weights(3, half_life=0)


def test_effective_sample_size_equals_n_for_flat_weights() -> None:
    assert fc.effective_sample_size([1.0] * 6) == pytest.approx(6.0)


def test_decay_costs_effective_sample_size() -> None:
    """Recency weighting is not free — 8 decayed games are worth fewer than 8."""
    n_eff = fc.effective_sample_size(fc.exponential_weights(8, half_life=4.0))
    assert 0 < n_eff < 8.0


def test_effective_sample_size_of_nothing_is_zero() -> None:
    assert fc.effective_sample_size([]) == 0.0
    assert fc.effective_sample_size([0.0, 0.0]) == 0.0


# --- shrinkage ----------------------------------------------------------------------


def test_shrink_is_halfway_when_sample_equals_constant() -> None:
    assert fc.shrink(observed=10.0, prior=0.0, n_eff=5.0, k=5.0) == pytest.approx(5.0)


def test_shrink_returns_prior_with_no_sample() -> None:
    assert fc.shrink(observed=99.0, prior=4.0, n_eff=0.0, k=10.0) == 4.0


def test_shrink_approaches_observed_with_large_sample() -> None:
    assert fc.shrink(observed=10.0, prior=0.0, n_eff=1000.0, k=5.0) == pytest.approx(9.95, abs=0.01)


def test_shrink_rejects_negative_constant() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        fc.shrink(1.0, 1.0, 1.0, -1.0)


def test_shrinkage_constant_is_small_when_players_genuinely_differ() -> None:
    """Big between-player spread, tight within-player: trust the player."""
    groups = [[1.0, 1.1, 0.9], [10.0, 10.1, 9.9], [20.0, 20.1, 19.9]]
    assert fc.shrinkage_constant(groups) < 1.0


def test_shrinkage_constant_is_large_when_spread_is_all_noise() -> None:
    """Groups drawn from one distribution have no real between-player signal."""
    rng = np.random.default_rng(0)
    groups = [list(rng.normal(5.0, 3.0, 8)) for _ in range(40)]
    assert fc.shrinkage_constant(groups) > 10.0


def test_shrinkage_constant_degrades_safely_on_thin_input() -> None:
    assert fc.shrinkage_constant([]) == 200.0
    assert fc.shrinkage_constant([[1.0]]) == 200.0
    assert fc.shrinkage_constant([[1.0], [2.0]]) == 200.0  # no within-group variance


# --- simulation draws ---------------------------------------------------------------


def test_negative_binomial_matches_requested_mean_and_overdisperses() -> None:
    rng = np.random.default_rng(1)
    draws = fc.negative_binomial_draws(10.0, dispersion=2.0, size=40_000, rng=rng)
    assert draws.mean() == pytest.approx(10.0, rel=0.05)
    assert draws.var() == pytest.approx(20.0, rel=0.10)


def test_negative_binomial_falls_back_to_poisson_when_not_overdispersed() -> None:
    rng = np.random.default_rng(2)
    draws = fc.negative_binomial_draws(6.0, dispersion=1.0, size=40_000, rng=rng)
    assert draws.var() == pytest.approx(6.0, rel=0.10)


def test_zero_mean_draws_are_all_zero() -> None:
    rng = np.random.default_rng(3)
    assert fc.negative_binomial_draws(0.0, 2.0, 100, rng).sum() == 0


def test_gamma_totals_scale_with_opportunity_count() -> None:
    rng = np.random.default_rng(4)
    counts = np.full(20_000, 10)
    totals = fc.gamma_total_draws(counts, per_unit_mean=4.5, per_unit_cv=1.1, rng=rng)
    assert totals.mean() == pytest.approx(45.0, rel=0.05)


def test_gamma_totals_are_zero_where_there_are_no_opportunities() -> None:
    rng = np.random.default_rng(5)
    counts = np.array([0, 0, 5])
    totals = fc.gamma_total_draws(counts, 4.0, 1.0, rng)
    assert totals[0] == 0.0 and totals[1] == 0.0 and totals[2] > 0.0


# --- the payoff: threshold bonuses fire at their true probability -------------------


def test_simulation_earns_partial_credit_for_a_bonus_the_mean_line_never_fires() -> None:
    """The bias documented in model/projections.py, repaired.

    An expected 95-yard rusher never clears the 100-yard bonus when a mean stat line is
    scored once, but clears it in a real fraction of simulated games.
    """
    priors = fc.PositionalPriors(season=2025, dispersion={("RB", "rush_att"): 1.4})
    expected = {"rush_att": 20.0, "rush_yd": 95.0, "rush_td": 0.5}

    from sleeper_ffm.scoring.engine import score

    point_estimate = score(expected, _SCORING)
    simulated = fc.simulate_points(expected, "RB", priors, _SCORING, n_sims=4000, seed=7)

    assert point_estimate == pytest.approx(12.5)  # 9.5 + 3.0 TD, no bonus
    assert simulated.mean > point_estimate


def test_simulation_produces_a_spread_and_ordered_quantiles() -> None:
    priors = fc.PositionalPriors(season=2025, dispersion={("WR", "rec_tgt"): 1.5})
    expected = {"rec_tgt": 8.0, "rec": 5.5, "rec_yd": 70.0, "rec_td": 0.4}
    dist = fc.simulate_points(expected, "WR", priors, _SCORING, n_sims=3000, seed=11)
    assert dist.floor < dist.median <= dist.mean + 1e-9
    assert dist.median < dist.ceiling
    assert dist.std > 0


def test_simulation_is_deterministic_under_a_fixed_seed() -> None:
    priors = fc.PositionalPriors(season=2025)
    expected = {"rush_att": 12.0, "rush_yd": 50.0, "rush_td": 0.3}
    a = fc.simulate_points(expected, "RB", priors, _SCORING, n_sims=500, seed=99)
    b = fc.simulate_points(expected, "RB", priors, _SCORING, n_sims=500, seed=99)
    assert a == b


def test_empty_stat_line_simulates_to_zero() -> None:
    dist = fc.simulate_points({}, "RB", fc.PositionalPriors(season=2025), _SCORING, n_sims=200)
    assert dist.mean == 0.0 and dist.ceiling == 0.0


def test_probability_over_is_monotonic() -> None:
    dist = fc.ForecastDistribution(mean=12.0, median=11.0, floor=4.0, ceiling=21.0, std=6.0)
    assert dist.probability_over(0.0) > dist.probability_over(12.0) > dist.probability_over(30.0)
    assert dist.probability_over(12.0) == pytest.approx(0.5, abs=0.01)


# --- projection assembly ------------------------------------------------------------


def _game(**kw: float) -> dict:
    base = {
        "carries": 0.0,
        "rushing_yards": 0.0,
        "rushing_tds": 0.0,
        "targets": 0.0,
        "receptions": 0.0,
        "receiving_yards": 0.0,
        "receiving_tds": 0.0,
        "attempts": 0.0,
        "completions": 0.0,
        "passing_yards": 0.0,
        "passing_tds": 0.0,
        "interceptions": 0.0,
    }
    base.update(kw)
    return base


def test_rate_quantities_skip_games_with_no_opportunity() -> None:
    """A game with zero carries must not enter the yards-per-carry sample as a 0.0."""
    series = fc._player_quantities([_game(carries=10, rushing_yards=50), _game(carries=0)])
    assert series["rush_att"] == [10.0, 0.0]
    assert series["yd_per_carry"] == [5.0]


def test_small_sample_efficiency_is_pulled_toward_the_prior() -> None:
    """Three carries at 9.0 YPC is a small sample, not a discovery."""
    priors = fc.PositionalPriors(
        season=2025,
        rates={("RB", "rush_att"): 10.0, ("RB", "yd_per_carry"): 4.2},
        constants={("RB", "rush_att"): 2.0, ("RB", "yd_per_carry"): 40.0},
    )
    stats, n_eff = fc.project_stat_line([_game(carries=3, rushing_yards=27)], "RB", priors)
    implied_ypc = stats["rush_yd"] / stats["rush_att"]
    assert 4.2 < implied_ypc < 5.0  # nowhere near the observed 9.0
    assert n_eff == 1.0


def test_context_multiplier_moves_volume_but_is_clamped() -> None:
    priors = fc.PositionalPriors(
        season=2025,
        rates={("RB", "rush_att"): 10.0, ("RB", "yd_per_carry"): 4.0},
        constants={("RB", "rush_att"): 1.0, ("RB", "yd_per_carry"): 1.0},
    )
    rows = [_game(carries=10, rushing_yards=40) for _ in range(6)]
    neutral, _ = fc.project_stat_line(rows, "RB", priors, context_multiplier=1.0)
    boosted, _ = fc.project_stat_line(rows, "RB", priors, context_multiplier=5.0)
    assert boosted["rush_att"] == pytest.approx(neutral["rush_att"] * fc._CONTEXT_CLAMP[1])


def test_touchdowns_are_not_scaled_by_context() -> None:
    """TD rate is already the noisiest term; it does not take a second multiplier."""
    priors = fc.PositionalPriors(
        season=2025,
        rates={("RB", "rush_att"): 10.0, ("RB", "rush_td_rate"): 0.05},
        constants={("RB", "rush_att"): 1.0, ("RB", "rush_td_rate"): 1.0},
    )
    rows = [_game(carries=10, rushing_tds=1) for _ in range(6)]
    neutral, _ = fc.project_stat_line(rows, "RB", priors, context_multiplier=1.0)
    boosted, _ = fc.project_stat_line(rows, "RB", priors, context_multiplier=1.3)
    implied_neutral = neutral["rush_td"] / neutral["rush_att"]
    implied_boosted = boosted["rush_td"] / boosted["rush_att"]
    # rel tolerance: project_stat_line rounds its output to 3 decimals.
    assert implied_neutral == pytest.approx(implied_boosted, rel=1e-4)


def test_no_history_projects_the_positional_prior() -> None:
    priors = fc.PositionalPriors(
        season=2025,
        rates={("WR", "rec_tgt"): 5.0, ("WR", "yd_per_target"): 8.0},
    )
    stats, n_eff = fc.project_stat_line([], "WR", priors)
    assert stats["rec_tgt"] == 5.0
    assert stats["rec_yd"] == pytest.approx(40.0)
    assert n_eff == 0.0


def test_interceptions_are_projected_for_quarterbacks() -> None:
    priors = fc.PositionalPriors(
        season=2025,
        rates={("QB", "pass_att"): 30.0, ("QB", "pass_int_rate"): 0.025},
        constants={("QB", "pass_att"): 1.0, ("QB", "pass_int_rate"): 1.0},
    )
    rows = [_game(attempts=30, interceptions=1) for _ in range(6)]
    stats, _ = fc.project_stat_line(rows, "QB", priors)
    assert stats["pass_int"] > 0.0


# --- recentring on a better mean ----------------------------------------------------


def test_recentred_distribution_keeps_its_shape() -> None:
    """The provider's mean wearing the simulation's spread."""
    dist = fc.ForecastDistribution(mean=10.0, median=9.0, floor=3.0, ceiling=19.0, std=5.0)
    out = dist.recentered_to(20.0)
    assert out.mean == 20.0
    assert out.floor == 6.0 and out.ceiling == 38.0
    # coefficient of variation is preserved
    assert out.std / out.mean == pytest.approx(dist.std / dist.mean)


def test_recentring_is_a_no_op_on_a_zero_distribution() -> None:
    zero = fc.ForecastDistribution(mean=0.0, median=0.0, floor=0.0, ceiling=0.0, std=0.0)
    assert zero.recentered_to(12.0) == zero
    live = fc.ForecastDistribution(mean=10.0, median=9.0, floor=3.0, ceiling=19.0, std=5.0)
    assert live.recentered_to(0.0) == live


# --- position gating ----------------------------------------------------------------


def test_positions_only_model_quantities_they_actually_produce() -> None:
    assert "pass_att" in fc.quantities_for("QB")
    assert "pass_att" not in fc.quantities_for("RB")
    assert "rec_tgt" not in fc.quantities_for("QB")
    assert "rush_att" in fc.quantities_for("WR")  # jet sweeps are real
    assert fc.quantities_for("K") == ()


def test_a_trick_play_pass_does_not_become_a_projection() -> None:
    """One halfback option pass must not give every back a passing projection."""
    priors = fc.PositionalPriors(
        season=2025,
        rates={("RB", "pass_att"): 0.005, ("RB", "pass_td_rate"): 0.43},
        constants={("RB", "pass_att"): 1.0, ("RB", "pass_td_rate"): 1.0},
    )
    rows = [_game(carries=10, attempts=1, passing_tds=1)] + [_game(carries=10) for _ in range(5)]
    stats, _ = fc.project_stat_line(rows, "RB", priors)
    assert stats["pass_att"] == 0.0
    assert stats["pass_td"] == 0.0
