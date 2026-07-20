"""In-house weekly player forecasts — volume x efficiency, shrunk, then simulated.

The engines around this one are all *descriptive*: they measure what happened
(:mod:`~sleeper_ffm.model.sabermetrics`), strip schedule effects out of it
(:mod:`~sleeper_ffm.model.opponent_adjusted`), or flag it as unsustainable
(:mod:`~sleeper_ffm.model.regression`). None of them answer "what will this player do
next week." :mod:`~sleeper_ffm.model.projections` answers it by asking rotowire. This
module answers it from the box scores, so the answer can be audited, adjusted for this
league's scoring, and — critically — *scored against* rotowire out of sample.

The model
---------
Fantasy points are not forecast directly. Points are a noisy function of a few stable
quantities and one very unstable one, so each is forecast on its own scale and
recombined::

    opportunities (stable)  x  efficiency (less stable)  ->  yards
    opportunities           x  scoring rate (unstable)   ->  touchdowns
    yards + touchdowns + receptions  ->  score under league rules

Three ideas do the actual work:

**1. Recency weighting.** Week 12 tells you more than week 1. Games are weighted by an
exponential decay with a half-life in games (:func:`exponential_weights`), so the
profile tracks in-season role changes without discarding the earlier sample outright.

**2. Empirical-Bayes shrinkage toward a positional prior.** A running back with three
carries at 9.0 yards per carry has not discovered anything; he has a small sample. Every
rate is pulled toward its positional mean by :func:`shrink`, with the pull set by
:func:`shrinkage_constant` — the method-of-moments estimator ``k = within_var /
between_var``. That ratio is *derived from the season's own data*, not hand-tuned, and it
does the right thing automatically per quantity: carries-per-game varies a lot between
players and little within them (low ``k``, trust the player), while yards-per-carry is
the reverse (high ``k``, trust the prior). The weight given to observed data is
``n_eff / (n_eff + k)``, where ``n_eff`` is the *effective* sample size of the decayed
weights (:func:`effective_sample_size`) — so recency weighting correctly costs sample
size instead of being a free lunch.

**3. Simulation rather than a point estimate.** The expected line is pushed through
:func:`simulate_points`: counts drawn negative-binomial (over-dispersed — real usage is
lumpier than Poisson), per-opportunity yards gamma, touchdowns Poisson, catches binomial.
Each of the N draws is scored by :func:`sleeper_ffm.scoring.engine.score`, giving a
*distribution* of fantasy points.

That last choice pays for itself twice. Start/sit needs a floor and a ceiling, not a
mean — and this yields p10/p90 directly. And it repairs the exact bias documented in
:mod:`sleeper_ffm.model.projections`: scoring a mean stat line with a step function never
fires a 100-yard bonus at 95.4 expected yards, but scoring 2,000 simulated lines fires it
in precisely the fraction of draws that clear it. The bonus is earned at its true
probability instead of being rounded away.

Context adjustment
------------------
Two multipliers already computed elsewhere are applied to the volume-driven components:
the opponent's defense-vs-position index (:func:`sleeper_ffm.model.schedule_strength.compute_dvp`)
and the Vegas game environment (:func:`sleeper_ffm.model.vegas.environment_multiplier`).
Both are deliberately applied to *yards and opportunity*, never to touchdowns directly —
touchdown rate is already the noisiest term in the model and does not need a second
multiplier stacked on it.

Measured accuracy — this model does NOT beat the free projection
----------------------------------------------------------------
``run_forecast_backtest(2024, 2025)``, 4,069 player-weeks from week 5, mean absolute
error in league fantasy points per player-week::

    provider (rotowire)   4.497   <- best
    model (this module)   4.739
    season-to-date mean   4.768
    last-4 mean           4.895

So the model beats the naive baselines, by a margin (0.6% over season-to-date) too thin
to care about, and **loses to rotowire by 5.4%**. Blending the two is no escape: the
correlation between the model's errors and the provider's is **0.935**, and the best
blend (20% model) improves on the provider by 0.07% — noise. The two are not independent
views. This model largely rediscovers the volume-times-efficiency signal the provider
already has, slightly worse.

That result is the reason :meth:`ForecastDistribution.recentered_to` exists. The division
of labour it implies is real and worth stating plainly:

* **Use the provider for the mean.** It is better and it is free.
* **Use this module for the shape.** The provider ships one number per player. Start/sit
  needs a floor and a ceiling, and a distribution is the only way to price a threshold
  bonus honestly. Nothing else in this repo produces one.
* **Keep this module as the fallback.** The provider rides an undocumented endpoint. If
  it disappears, the in-house forecast degrades accuracy by ~5%, not to zero.

Do not quietly swap this model in as the primary point estimate on the strength of its
internals looking principled. The measurement says otherwise.

Honest limits
-------------
* **No injury or depth-chart input.** A player who was inactive projects from the games
  he did play. :mod:`~sleeper_ffm.model.news_feed` knows about injuries; this does not
  consume it yet.
* **Positional priors are league-wide, not role-aware.** A committee back and a bell-cow
  shrink toward the same carries prior. Role clustering would be the next real
  improvement.
* **QB rushing is modeled, QB passing efficiency is thin.** Completion percentage is
  shrunk but air yards and pressure are not used.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import polars as pl

from sleeper_ffm.config import DEFAULT_VALUE_SEASON
from sleeper_ffm.scoring.engine import score

log = logging.getLogger(__name__)

_SKILL: frozenset[str] = frozenset({"QB", "RB", "WR", "TE"})

# Half-life in games for recency decay: a game 4 games back counts half as much as the
# most recent one. Short enough to track a role change, long enough that one outlier
# cannot dominate.
_HALF_LIFE_GAMES = 4.0

# Monte-Carlo draws per player. 2000 puts the standard error of the p10/p90 estimates
# well under 0.1 fantasy points, which is far finer than the model's real accuracy.
_DEFAULT_SIMS = 2000
_DEFAULT_SEED = 20260719

# Floor on the negative-binomial dispersion ratio (var/mean). At 1.0 the draw degenerates
# to Poisson; real usage counts are over-dispersed, so this only binds for tiny samples.
_MIN_DISPERSION = 1.05
# Cap on how far context multipliers can move a projection, applied to their product.
# Keeps a soft matchup in a high total from compounding into an implausible swing.
_CONTEXT_CLAMP = (0.75, 1.30)

# nflverse weekly column -> the model's internal quantity names.
_RUSH_ATT = "carries"
_RUSH_YD = "rushing_yards"
_RUSH_TD = "rushing_tds"
_TGT = "targets"
_REC = "receptions"
_REC_YD = "receiving_yards"
_REC_TD = "receiving_tds"
_PASS_ATT = "attempts"
_PASS_CMP = "completions"
_PASS_YD = "passing_yards"
_PASS_TD = "passing_tds"
_PASS_INT = "interceptions"


# --- pure math primitives -----------------------------------------------------------


def exponential_weights(n: int, half_life: float = _HALF_LIFE_GAMES) -> list[float]:
    """Recency weights for ``n`` games, oldest first, newest weighted 1.0.

    Args:
        n: Number of games.
        half_life: Games back at which weight halves. Must be > 0.

    Returns:
        Weights oldest-to-newest, normalized so the most recent game weighs 1.0.
    """
    if n <= 0:
        return []
    if half_life <= 0:
        raise ValueError("half_life must be positive")
    decay = 0.5 ** (1.0 / half_life)
    # index 0 is the oldest of n games, so it is (n-1) games back from the newest.
    return [decay ** (n - 1 - i) for i in range(n)]


def effective_sample_size(weights: Sequence[float]) -> float:
    """Kish effective sample size of a weight vector: ``(sum w)^2 / sum(w^2)``.

    Recency weighting buys relevance at the cost of sample. This is the honest count of
    how many equally-weighted games the decayed sample is actually worth, and it is what
    :func:`shrink` should be given — not the raw game count.

    Args:
        weights: Non-negative weights.

    Returns:
        Effective sample size in ``[0, len(weights)]``.
    """
    total = sum(weights)
    if total <= 0:
        return 0.0
    return (total * total) / sum(w * w for w in weights)


def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    """Weighted arithmetic mean. Returns 0.0 when the weights sum to zero."""
    total = sum(weights)
    if total <= 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights, strict=True)) / total


def shrink(observed: float, prior: float, n_eff: float, k: float) -> float:
    """Pull an observed rate toward a prior by its effective sample size.

    The posterior mean of a normal hierarchical model: ``(n*observed + k*prior) / (n+k)``.
    With ``n_eff == k`` the result sits halfway between observed and prior.

    Args:
        observed: The player's own (recency-weighted) rate.
        prior: The positional mean to shrink toward.
        n_eff: Effective sample size behind ``observed``.
        k: Shrinkage constant from :func:`shrinkage_constant`.

    Returns:
        The shrunk estimate. Returns ``prior`` when there is no sample at all.
    """
    if n_eff <= 0:
        return prior
    if k < 0:
        raise ValueError("k must be non-negative")
    return (n_eff * observed + k * prior) / (n_eff + k)


def shrinkage_constant(groups: Sequence[Sequence[float]]) -> float:
    """Estimate ``k = within_variance / between_variance`` from grouped observations.

    Method of moments for a one-way random-effects model. ``within`` is the pooled
    variance of observations around their own group's mean; ``between`` is the variance
    of the group means, *corrected* for the sampling noise those means carry
    (``within / mean_group_size``) — without that correction ``between`` is inflated and
    every quantity looks more player-driven than it is.

    A quantity where players genuinely differ (carries per game) gets a small ``k``: trust
    the player. A quantity that is mostly noise (yards per carry) gets a large ``k``: trust
    the prior. Nothing is hand-tuned.

    Args:
        groups: One sequence of observations per player. Groups with < 2 observations
            contribute to the group-mean spread but not to the within-variance estimate.

    Returns:
        The shrinkage constant, clamped to ``[0.5, 200.0]``. Returns 1e6 (shrink almost
        entirely to the prior) when between-group variance is not distinguishable from
        noise, and 200.0 when there is too little data to estimate at all.
    """
    usable = [list(g) for g in groups if len(g) >= 1]
    if len(usable) < 2:
        return 200.0

    within_numerator = 0.0
    within_dof = 0
    for g in usable:
        if len(g) < 2:
            continue
        mean_g = sum(g) / len(g)
        within_numerator += sum((x - mean_g) ** 2 for x in g)
        within_dof += len(g) - 1
    if within_dof == 0:
        return 200.0
    within = within_numerator / within_dof

    means = [sum(g) / len(g) for g in usable]
    grand = sum(means) / len(means)
    observed_between = sum((m - grand) ** 2 for m in means) / (len(means) - 1)
    mean_group_size = sum(len(g) for g in usable) / len(usable)
    between = observed_between - (within / mean_group_size)

    if between <= 0:
        # Group means differ by no more than sampling noise explains: no real between-
        # player signal, so shrink essentially all the way to the prior.
        return 1e6
    return min(200.0, max(0.5, within / between))


def negative_binomial_draws(
    mean: float,
    dispersion: float,
    size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Draw over-dispersed counts via a gamma-Poisson mixture.

    Args:
        mean: Expected count (>= 0).
        dispersion: Variance-to-mean ratio; values <= 1 fall back to Poisson.
        size: Number of draws.
        rng: Seeded generator.

    Returns:
        Integer counts of length ``size``.
    """
    if mean <= 0:
        return np.zeros(size, dtype=int)
    if dispersion <= 1.0:
        return rng.poisson(mean, size)
    # var = mean * dispersion  =>  shape r = mean / (dispersion - 1)
    shape = mean / (dispersion - 1.0)
    lam = rng.gamma(shape=shape, scale=(dispersion - 1.0), size=size)
    return rng.poisson(lam)


def gamma_total_draws(
    counts: np.ndarray,
    per_unit_mean: float,
    per_unit_cv: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Draw total yards as a sum of ``counts`` iid gamma per-opportunity gains.

    The sum of ``n`` iid ``Gamma(shape, scale)`` variables is ``Gamma(n*shape, scale)``,
    so the total is drawn exactly in one step rather than by looping per opportunity.

    Args:
        counts: Per-draw opportunity counts.
        per_unit_mean: Mean yards per opportunity.
        per_unit_cv: Coefficient of variation of yards per opportunity.
        rng: Seeded generator.

    Returns:
        Total yards per draw; zero wherever ``counts`` is zero.
    """
    out = np.zeros(len(counts), dtype=float)
    if per_unit_mean <= 0:
        return out
    cv = max(0.15, per_unit_cv)
    shape = 1.0 / (cv * cv)
    scale = per_unit_mean / shape
    nonzero = counts > 0
    if not nonzero.any():
        return out
    out[nonzero] = rng.gamma(shape=shape * counts[nonzero], scale=scale)
    return out


# --- forecast types -----------------------------------------------------------------


@dataclass(frozen=True)
class ForecastDistribution:
    """The simulated fantasy-point distribution for one player-week."""

    mean: float
    median: float
    floor: float  # p10
    ceiling: float  # p90
    std: float

    def recentered_to(self, target_mean: float) -> ForecastDistribution:
        """Rescale this distribution to a new mean, preserving its shape.

        The measured division of labour (see the module's *Measured accuracy* note): the
        provider forecasts the *mean* better than this model does, while this model is
        the only source of a *shape* — floor, ceiling, spread. Multiplicative rescaling
        keeps the coefficient of variation and the skew, so the result is the provider's
        point estimate wearing the simulation's distribution.

        Args:
            target_mean: The mean to recentre on, typically a provider projection.

        Returns:
            A rescaled distribution. Returns ``self`` unchanged when either mean is
            non-positive, since the ratio is undefined and a zero projection has no
            shape to preserve.
        """
        if self.mean <= 0 or target_mean <= 0:
            return self
        factor = target_mean / self.mean
        return ForecastDistribution(
            mean=round(target_mean, 2),
            median=round(self.median * factor, 2),
            floor=round(self.floor * factor, 2),
            ceiling=round(self.ceiling * factor, 2),
            std=round(self.std * factor, 2),
        )

    def probability_over(self, threshold: float) -> float:
        """Normal-approximation probability of exceeding ``threshold``.

        Provided for quick comparisons; the simulated quantiles above are exact and
        should be preferred when the distribution is visibly skewed (it usually is).
        """
        if self.std <= 0:
            return 1.0 if self.mean > threshold else 0.0
        z = (self.mean - threshold) / self.std
        return round(0.5 * math.erfc(-z / math.sqrt(2.0)), 4)


@dataclass(frozen=True)
class PlayerForecast:
    """One player's projected week, from box scores, scored under league rules."""

    player_id: str
    name: str
    position: str
    team: str
    opponent: str
    season: int
    week: int
    points: ForecastDistribution
    expected_stats: dict[str, float] = field(default_factory=dict)
    games_used: int = 0
    n_eff: float = 0.0
    context_multiplier: float = 1.0

    @property
    def opportunity(self) -> float:
        """Projected touches: carries plus targets."""
        return self.expected_stats.get("rush_att", 0.0) + self.expected_stats.get("rec_tgt", 0.0)


@dataclass(frozen=True)
class PositionalPriors:
    """League-wide per-position means and shrinkage constants for one season.

    ``rates`` holds the prior mean for each modeled quantity; ``constants`` holds the
    matching ``k`` from :func:`shrinkage_constant`. Both are keyed
    ``(position, quantity)``.
    """

    season: int
    rates: dict[tuple[str, str], float] = field(default_factory=dict)
    constants: dict[tuple[str, str], float] = field(default_factory=dict)
    dispersion: dict[tuple[str, str], float] = field(default_factory=dict)

    def prior(self, position: str, quantity: str, default: float = 0.0) -> float:
        """Prior mean for a position/quantity pair."""
        return self.rates.get((position, quantity), default)

    def constant(self, position: str, quantity: str, default: float = 20.0) -> float:
        """Shrinkage constant for a position/quantity pair."""
        return self.constants.get((position, quantity), default)


# Quantities modeled as per-game volume (shrunk toward a positional per-game mean).
_VOLUME_QUANTITIES = ("rush_att", "rec_tgt", "pass_att")
# Quantities modeled as per-opportunity rates (shrunk toward a positional rate).
_RATE_QUANTITIES = (
    "yd_per_carry",
    "yd_per_target",
    "catch_rate",
    "yd_per_pass",
    "cmp_rate",
    "pass_int_rate",
)
# Touchdown rates, per opportunity. Shrunk hardest — this is the noisiest term.
_TD_QUANTITIES = ("rush_td_rate", "rec_td_rate", "pass_td_rate")

_ALL_QUANTITIES = _VOLUME_QUANTITIES + _RATE_QUANTITIES + _TD_QUANTITIES

# Which quantities each position actually models. Without this split, one halfback option
# pass in a season produces an "RB pass_td_rate" prior of 0.43 fitted on a handful of
# trick plays, and every back with a single pass attempt inherits it. Non-QBs do not
# throw; QBs do not run routes. Rushing is modeled for every position (jet sweeps and
# scrambles are both real) and receiving for every non-QB.
_PASSING = ("pass_att", "yd_per_pass", "cmp_rate", "pass_td_rate", "pass_int_rate")
_RUSHING = ("rush_att", "yd_per_carry", "rush_td_rate")
_RECEIVING = ("rec_tgt", "yd_per_target", "catch_rate", "rec_td_rate")

_QUANTITIES_BY_POSITION: dict[str, tuple[str, ...]] = {
    "QB": _PASSING + _RUSHING,
    "RB": _RUSHING + _RECEIVING,
    "WR": _RUSHING + _RECEIVING,
    "TE": _RUSHING + _RECEIVING,
}


def quantities_for(position: str) -> tuple[str, ...]:
    """Quantities modeled for a position. Unknown positions model nothing."""
    return _QUANTITIES_BY_POSITION.get(position, ())


def _player_quantities(rows: list[dict]) -> dict[str, list[float]]:
    """Per-game series for each modeled quantity from one player's weekly rows."""
    out: dict[str, list[float]] = {q: [] for q in _ALL_QUANTITIES}
    for row in rows:
        rush_att = _f(row.get(_RUSH_ATT))
        tgt = _f(row.get(_TGT))
        pass_att = _f(row.get(_PASS_ATT))

        out["rush_att"].append(rush_att)
        out["rec_tgt"].append(tgt)
        out["pass_att"].append(pass_att)

        # Rates are only defined on games where the opportunity existed. Appending a 0
        # for a game with no carries would drag the efficiency estimate toward zero for
        # a reason that has nothing to do with efficiency.
        if rush_att > 0:
            out["yd_per_carry"].append(_f(row.get(_RUSH_YD)) / rush_att)
            out["rush_td_rate"].append(_f(row.get(_RUSH_TD)) / rush_att)
        if tgt > 0:
            out["yd_per_target"].append(_f(row.get(_REC_YD)) / tgt)
            out["catch_rate"].append(min(1.0, _f(row.get(_REC)) / tgt))
            out["rec_td_rate"].append(_f(row.get(_REC_TD)) / tgt)
        if pass_att > 0:
            out["yd_per_pass"].append(_f(row.get(_PASS_YD)) / pass_att)
            out["cmp_rate"].append(min(1.0, _f(row.get(_PASS_CMP)) / pass_att))
            out["pass_td_rate"].append(_f(row.get(_PASS_TD)) / pass_att)
            out["pass_int_rate"].append(_f(row.get(_PASS_INT)) / pass_att)
    return out


def build_priors(season: int | None = None, min_games: int = 3) -> PositionalPriors:
    """Derive positional prior means and shrinkage constants from a season's box scores.

    Args:
        season: Season to fit on. Defaults to :data:`~sleeper_ffm.config.DEFAULT_VALUE_SEASON`.
        min_games: Players below this game count are excluded from the fit (they carry
            almost no information and inflate the within-variance estimate).

    Returns:
        Priors for every skill position present in the data.
    """
    from sleeper_ffm.nflverse.loader import load_weekly

    season = season or DEFAULT_VALUE_SEASON
    weekly = load_weekly([season])
    if weekly.is_empty():
        log.warning("forecast: no weekly data for %s; priors will be empty", season)
        return PositionalPriors(season=season)

    weekly = weekly.filter(pl.col("season_type") == "REG")
    priors = PositionalPriors(season=season)

    for position in sorted(_SKILL):
        pos_df = weekly.filter(pl.col("position") == position)
        if pos_df.is_empty():
            continue
        by_player: dict[str, list[dict]] = {}
        for row in pos_df.iter_rows(named=True):
            by_player.setdefault(str(row["player_id"]), []).append(row)

        series_by_player = {
            pid: _player_quantities(rows)
            for pid, rows in by_player.items()
            if len(rows) >= min_games
        }
        if not series_by_player:
            continue

        for quantity in quantities_for(position):
            groups = [s[quantity] for s in series_by_player.values() if s[quantity]]
            flat = [x for g in groups for x in g]
            if not flat:
                continue
            priors.rates[(position, quantity)] = sum(flat) / len(flat)
            priors.constants[(position, quantity)] = shrinkage_constant(groups)
            if quantity in _VOLUME_QUANTITIES:
                priors.dispersion[(position, quantity)] = _dispersion(groups)

    log.info(
        "forecast: fitted priors on %s (%d position/quantity pairs)",
        season,
        len(priors.rates),
    )
    return priors


def _dispersion(groups: Sequence[Sequence[float]]) -> float:
    """Pooled within-player variance-to-mean ratio for a count quantity."""
    numerator = 0.0
    dof = 0
    total = 0.0
    count = 0
    for g in groups:
        if len(g) < 2:
            continue
        mean_g = sum(g) / len(g)
        numerator += sum((x - mean_g) ** 2 for x in g)
        dof += len(g) - 1
        total += sum(g)
        count += len(g)
    if dof == 0 or count == 0 or total <= 0:
        return _MIN_DISPERSION
    within = numerator / dof
    mean = total / count
    return max(_MIN_DISPERSION, within / mean) if mean > 0 else _MIN_DISPERSION


def project_stat_line(
    rows: list[dict],
    position: str,
    priors: PositionalPriors,
    context_multiplier: float = 1.0,
) -> tuple[dict[str, float], float]:
    """Project one player's expected component stat line for a single game.

    Args:
        rows: The player's weekly box-score rows, oldest first.
        position: Sleeper position code.
        priors: Positional priors from :func:`build_priors`.
        context_multiplier: Combined matchup/game-environment multiplier applied to
            volume and yardage. Touchdown rates are deliberately left unmultiplied.

    Returns:
        ``(expected_stats, n_eff)`` where ``expected_stats`` is keyed in Sleeper's stat
        vocabulary, ready for :func:`sleeper_ffm.scoring.engine.score`.
    """
    series = _player_quantities(rows)
    modeled = quantities_for(position)

    def estimate(quantity: str) -> tuple[float, float]:
        # A quantity outside this position's model contributes nothing, even when the
        # box score has a stray value for it (a wideout's one trick-play pass).
        if quantity not in modeled:
            return 0.0, 0.0
        values = series[quantity]
        prior = priors.prior(position, quantity)
        if not values:
            return prior, 0.0
        weights = exponential_weights(len(values))
        n_eff = effective_sample_size(weights)
        observed = weighted_mean(values, weights)
        k = priors.constant(position, quantity)
        return shrink(observed, prior, n_eff, k), n_eff

    rush_att, n_rush = estimate("rush_att")
    rec_tgt, n_tgt = estimate("rec_tgt")
    pass_att, n_pass = estimate("pass_att")
    ypc, _ = estimate("yd_per_carry")
    ypt, _ = estimate("yd_per_target")
    catch_rate, _ = estimate("catch_rate")
    yp_pass, _ = estimate("yd_per_pass")
    cmp_rate, _ = estimate("cmp_rate")
    pass_int_rate, _ = estimate("pass_int_rate")
    rush_td_rate, _ = estimate("rush_td_rate")
    rec_td_rate, _ = estimate("rec_td_rate")
    pass_td_rate, _ = estimate("pass_td_rate")

    ctx = min(_CONTEXT_CLAMP[1], max(_CONTEXT_CLAMP[0], context_multiplier))
    rush_att *= ctx
    rec_tgt *= ctx
    pass_att *= ctx

    stats = {
        "rush_att": rush_att,
        "rush_yd": rush_att * ypc,
        "rush_td": rush_att * rush_td_rate,
        "rec_tgt": rec_tgt,
        "rec": rec_tgt * catch_rate,
        "rec_yd": rec_tgt * ypt,
        "rec_td": rec_tgt * rec_td_rate,
        "pass_att": pass_att,
        "pass_cmp": pass_att * cmp_rate,
        "pass_yd": pass_att * yp_pass,
        "pass_td": pass_att * pass_td_rate,
        "pass_int": pass_att * pass_int_rate,
    }
    n_eff = max(n_rush, n_tgt, n_pass)
    return {k: round(v, 3) for k, v in stats.items()}, round(n_eff, 3)


def simulate_points(
    expected: dict[str, float],
    position: str,
    priors: PositionalPriors,
    scoring: dict[str, float],
    n_sims: int = _DEFAULT_SIMS,
    seed: int = _DEFAULT_SEED,
) -> ForecastDistribution:
    """Simulate the fantasy-point distribution implied by an expected stat line.

    Each draw samples counts (negative binomial), per-opportunity yards (gamma),
    receptions (binomial), and touchdowns (Poisson), then scores the resulting line with
    the league's own scoring engine. Because every draw is scored individually, threshold
    bonuses fire in exactly the fraction of games that clear them.

    Args:
        expected: Expected stat line from :func:`project_stat_line`.
        position: Sleeper position code.
        priors: Positional priors (supplies count dispersion).
        scoring: League scoring settings.
        n_sims: Number of Monte-Carlo draws.
        seed: RNG seed for determinism.

    Returns:
        The simulated distribution.
    """
    rng = np.random.default_rng(seed)

    rush_att = expected.get("rush_att", 0.0)
    rec_tgt = expected.get("rec_tgt", 0.0)
    pass_att = expected.get("pass_att", 0.0)

    carries = negative_binomial_draws(
        rush_att, priors.dispersion.get((position, "rush_att"), 1.4), n_sims, rng
    )
    targets = negative_binomial_draws(
        rec_tgt, priors.dispersion.get((position, "rec_tgt"), 1.4), n_sims, rng
    )
    attempts = negative_binomial_draws(
        pass_att, priors.dispersion.get((position, "pass_att"), 1.2), n_sims, rng
    )

    ypc = _safe_div(expected.get("rush_yd", 0.0), rush_att)
    ypt = _safe_div(expected.get("rec_yd", 0.0), rec_tgt)
    ypa = _safe_div(expected.get("pass_yd", 0.0), pass_att)
    catch_rate = min(1.0, _safe_div(expected.get("rec", 0.0), rec_tgt))
    cmp_rate = min(1.0, _safe_div(expected.get("pass_cmp", 0.0), pass_att))

    rush_yd = gamma_total_draws(carries, ypc, 1.10, rng)
    rec_yd = gamma_total_draws(targets, ypt, 1.25, rng)
    pass_yd = gamma_total_draws(attempts, ypa, 0.55, rng)

    receptions = rng.binomial(targets, catch_rate) if catch_rate > 0 else np.zeros(n_sims, int)
    completions = rng.binomial(attempts, cmp_rate) if cmp_rate > 0 else np.zeros(n_sims, int)

    rush_td = rng.poisson(max(0.0, expected.get("rush_td", 0.0)), n_sims)
    rec_td = rng.poisson(max(0.0, expected.get("rec_td", 0.0)), n_sims)
    pass_td = rng.poisson(max(0.0, expected.get("pass_td", 0.0)), n_sims)
    pass_int = rng.poisson(max(0.0, expected.get("pass_int", 0.0)), n_sims)

    points = np.empty(n_sims, dtype=float)
    for i in range(n_sims):
        points[i] = score(
            {
                "rush_att": float(carries[i]),
                "rush_yd": float(rush_yd[i]),
                "rush_td": float(rush_td[i]),
                "rec": float(receptions[i]),
                "rec_tgt": float(targets[i]),
                "rec_yd": float(rec_yd[i]),
                "rec_td": float(rec_td[i]),
                "pass_att": float(attempts[i]),
                "pass_cmp": float(completions[i]),
                "pass_yd": float(pass_yd[i]),
                "pass_td": float(pass_td[i]),
                "pass_int": float(pass_int[i]),
            },
            scoring,
        )

    return ForecastDistribution(
        mean=round(float(points.mean()), 2),
        median=round(float(np.median(points)), 2),
        floor=round(float(np.percentile(points, 10)), 2),
        ceiling=round(float(np.percentile(points, 90)), 2),
        std=round(float(points.std()), 2),
    )


def forecast_player(
    rows: list[dict],
    player_id: str,
    name: str,
    position: str,
    team: str,
    opponent: str,
    season: int,
    week: int,
    priors: PositionalPriors,
    scoring: dict[str, float],
    context_multiplier: float = 1.0,
    n_sims: int = _DEFAULT_SIMS,
    seed: int = _DEFAULT_SEED,
) -> PlayerForecast:
    """Project and simulate one player-week end to end.

    Args:
        rows: The player's weekly box-score rows, oldest first.
        player_id: Identifier carried through to the result.
        name: Display name.
        position: Sleeper position code.
        team: Player's team abbreviation.
        opponent: Opponent abbreviation for the projected week.
        season: Season being projected.
        week: Week being projected.
        priors: Positional priors from :func:`build_priors`.
        scoring: League scoring settings.
        context_multiplier: Combined matchup and game-environment multiplier.
        n_sims: Monte-Carlo draws.
        seed: RNG seed.

    Returns:
        The player's forecast, including the simulated point distribution.
    """
    expected, n_eff = project_stat_line(rows, position, priors, context_multiplier)
    distribution = simulate_points(expected, position, priors, scoring, n_sims=n_sims, seed=seed)
    return PlayerForecast(
        player_id=player_id,
        name=name,
        position=position,
        team=team,
        opponent=opponent,
        season=season,
        week=week,
        points=distribution,
        expected_stats=expected,
        games_used=len(rows),
        n_eff=n_eff,
        context_multiplier=round(context_multiplier, 4),
    )


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else 0.0


def _f(value: object) -> float:
    """Coerce a possibly-null numeric cell to float."""
    if value is None:
        return 0.0
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(out) else out
