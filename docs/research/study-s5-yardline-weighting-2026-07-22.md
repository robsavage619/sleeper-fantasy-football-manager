# S5 — Yard-line weighting beats the engine's red-zone bucket

Date: 2026-07-22
Prompted by: `docs/research/q2-td-regression-2026-07-22.md`
Data: nflverse play-by-play 2016–2025. Fit 2016–2023, scored 2024–25 out of sample.

## The conflict

The Q2 literature review found published work (RotoViz, PFF, Fantasy Points)
arguing that red-zone *bucketing* is the wrong construction for expected
touchdowns — a carry from the 1-yard line converts at roughly 53.8% and one from
the 17 at 3.6%, and treating them as the same event throws that away. RotoViz
measured zone-bucketed touchdowns predicting next-season touchdowns *worse* than
raw touchdowns (r² 0.029 vs 0.079).

The engine does exactly what that criticism targets. `sabermetrics.py` sets
`is_redzone = yardline_100 <= 20` and builds four buckets from it, and
`regression.py` prices every opportunity off those buckets.

This is not, strictly, a contradiction of our own eval. The passing
`regression.redzone_beats_yardage_oos` scenario compares red-zone-opportunity
against a cruder *yardage* baseline and wins; the literature compares zone
bucketing against *raw touchdowns* and finer weighting. Both can be true. So
rather than pick a side, the question was settled by measurement.

## What the bucket throws away

Touchdown rate per carry, running backs, fitted on 2016–2023:

| Yard line | TD rate per carry |
|---|---|
| 1–5 | 39.3% |
| 6–10 | 10.6% |
| 11–20 | 4.2% |
| 21–40 | 1.0% |
| 41+ | 0.3% |

The engine's red-zone bucket spans the first three rows. A carry from the 3 and a
carry from the 18 are priced identically, despite a roughly ninefold difference in
conversion.

## Result

Predicting season touchdown totals for 2024–25, fitting on 2016–2023, for players
with at least 30 opportunities (n = 511). Mean absolute error:

| Model | MAE | vs engine |
|---|---|---|
| Two-bucket (engine today) | 1.4758 | — |
| Yard-line-weighted (5 bins) | 1.4016 | **+5.03%** |

By position:

| Position | n | two-bucket | yard-line | improvement |
|---|---|---|---|---|
| RB | 186 | 1.4680 | 1.3182 | **+10.20%** |
| WR | 230 | 1.5099 | 1.4602 | +3.29% |
| TE | 95 | 1.4086 | 1.4228 | −1.01% |

Running back is where the prize is, which is mechanically sensible: back
touchdowns are goal-line events, so collapsing the goal line into a 20-yard bucket
costs the most there. The tight end result is slightly negative on a small sample
and should be read as "no effect", not as a reason to keep bucketing.

## Recommendation

Replace the binary `is_redzone` flag with yard-line bins in
`sabermetrics.redzone_td_rates` and `player_redzone_opportunities`, and update
`regression.compute_redzone_td_regression` to price against them. This is a
contained change but it touches the bucket structure several functions share, and
it will move the `regression.redzone_beats_yardage_oos` baseline, so it deserves
its own reviewed commit rather than being folded into research work.

Expected gain: roughly 5% lower expected-touchdown error overall, 10% at running
back — on the engine surface that drives buy-low and sell-high calls.

## Follow-up: the smooth model does not do better (2026-07-22)

Implementing this raised the obvious question the first limitation below flags, so it
was measured before the bins were committed. Twelve shapes were scored — the two-bucket
baseline, eight bin sets from 5 to 9 bins, and three fitted continuous functions of
`yardline_100` (logistic in `log(y)`, logistic with a cubic in `log(y)`, and per-yard
empirical rates shrunk toward a smooth prior) — on the pooled 2016-2023 fit and on all
nine consecutive-season splits.

The smooth fits lost. A logistic in `log(y)` gained only 1.26% on the pooled protocol
against these bins' 5.03%: the true conversion curve is steeper at the goal line and
flatter past midfield than a log-linear logit can bend. The cubic version closed most
of the gap (4.17%) without ever beating bins. Per-yard empirical rates won the pooled
fit (5.47%) and lost the single-season splits, which is the regime that matters —
`redzone_td_rates` is handed one season in production.

Across the nine single-season splits every bin set landed between 4.91% and 5.16% mean
improvement: indistinguishable. The five bins below have the best worst-case split
(+1.90%, vs +0.57% for the eight-bin variant), so they were kept. Finer bins buy nothing
and thin the goal-line cells.

So the limitation is resolved in the opposite direction from the guess: bin, and bin
coarsely.

Shipped in `sabermetrics.YARDLINE_BINS`. On the tier-1 eval's split (fit 2024, score
2025, n=235) the gain over the *yardage* baseline goes from 19.34% to 24.55%, and the
eval floor was ratcheted 5% -> 20% so a revert to bucketing fails.

## Limitations

- Five hand-chosen bins, not a fitted continuous function of yard line. A smooth
  model would likely do better still; this was the cheapest test of the claim.
  *(Tested on implementation — it does not. See the follow-up above.)*
- The comparison is expected-TD accuracy against realised touchdowns in the same
  season, which measures pricing of opportunity rather than forecasting of future
  touchdowns. That is the right target for the regression engine's use, but it is
  not the same quantity RotoViz reported.
- No separation of receiving depth-of-target from field position; Q2 notes a
  target's value depends on both, and this tests only the latter.
