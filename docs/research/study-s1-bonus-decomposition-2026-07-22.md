# S1 — Bonus-aware decomposition of league-scored fantasy points

Date: 2026-07-22
Code: `src/sleeper_ffm/model/research/decomposition.py`
Data: nflverse weekly + play-by-play, 2016–2025 (3,852 player-seasons, ≥6 games)
Split: train ≤2022 pairs, holdout 2023→2024 and 2024→2025 pairs

## Question

This league pays threshold bonuses on top of full PPR: 2.5 for a 100-yard game,
5.0 for 200, 2.5 for a 40+ yard touchdown, 1.0 for a 20-carry game, 2.5 for 300
passing yards and 25 completions. Every public valuation — FantasyCalc, rotowire
projections, ADP — prices generic scoring. So: is there a player profile that
converts the same raw production into more bonus points than average, and is that
profile persistent enough to draft and trade on?

The trap is that bonus points mostly proxy for being good — a receiver with 1,400
yards clears 100 more often than one with 700. Counting raw bonus points would
rediscover "good players are good". So the measured quantity is the **residual**:
bonus points per game above what a player's own non-bonus production predicts,
fitted within position.

## Headline

**The trait hypothesis is a null everywhere except quarterback.** Bonus-proneness
does not persist year over year for running backs, receivers or tight ends at any
level worth acting on.

Persistence of the bonus residual (Pearson r between a player's season and his next):

| Position | train n | train r | holdout n | holdout r | captured pts/28-game season |
|---|---|---|---|---|---|
| QB | 200 | 0.367 | 63 | **0.557** | **12.4** |
| RB | 470 | 0.461 | 145 | 0.230 | 2.2 |
| WR | 752 | 0.211 | 249 | 0.166 | 1.1 |
| TE | 388 | 0.290 | 142 | 0.216 | 0.8 |

"Captured" is the honest edge: the out-of-sample r times the residual's standard
deviation, times 28 games. It is what you actually collect by preferring a
+1-standard-deviation bonus-prone player, not the raw top-to-bottom spread.

Running back looked like the second real effect on train data (r = 0.461) and
mostly evaporated out of sample (r = 0.230). That is the pattern of an
overfit — it is reported here as one rather than shipped.

The quarterback result survives and strengthens out of sample, but note where it
lands: this is a 10-team league that starts **one** quarterback. The single
position with a validated bonus edge is the position where a 12-point season
advantage is worth the least. It is real, and it is small.

### Structural bonus premium (not a trait — a property of the rules)

Separately from any player trait, the scoring rules mechanically favour some
positions. Share of total league-scored points coming from bonuses:

| Position | base pts/game | bonus pts/game | bonus share |
|---|---|---|---|
| QB | 15.28 | 1.588 | 8.6% |
| RB | 8.59 | 0.321 | 2.4% |
| WR | 7.98 | 0.271 | 2.3% |
| TE | 5.88 | 0.065 | 0.6% |

This needs no persistence to be actionable — it is arithmetic. A generic-scoring
market understates quarterbacks by roughly 6 percentage points relative to tight
ends in this league.

## The finding that matters more: the engine is scoring bonuses incompletely

While measuring the above, the study surfaced a live defect. `scoring/engine.py`
derives threshold bonuses from aggregate stat lines, but the 40+ yard touchdown
bonuses (`pass_td_40p`, `rush_td_40p`, `rec_td_40p`, 2.5 points each) cannot be
derived that way — a weekly box score records that a touchdown happened, not how
far it travelled. They silently score as zero on every historical read. The
engine's docstring calls this "a documented, small under-credit".

It is small as a share of total points (~1–2%) and large as a share of the thing
it distorts: **21–35% of all bonus points are missing**, measured on 2024–25.

That flows straight into `model/mispricing.py`, whose entire output is the ratio
`our_fp / generic_fp`. Both terms come from the aggregate path, so the leverage
that drives every mispricing call is understated:

| Position | leverage as computed | true leverage | understated by | p95 |
|---|---|---|---|---|
| QB | 1.0736 | 1.1003 | 2.68 pp | 6.28 pp |
| WR | 1.0193 | 1.0317 | 1.24 pp | 4.73 pp |
| RB | 1.0274 | 1.0336 | 0.62 pp | 3.10 pp |
| TE | 1.0081 | 1.0117 | 0.35 pp | 2.42 pp |

(fantasy-relevant players only, ≥5 base points/game)

Individual 2025 starters are understated by far more than the average. TreVeyon
Henderson's leverage reads 1.024 and is truly 1.073; C.J. Stroud reads 1.035
against a true 1.082. These are exactly the big-play profiles the mispricing
engine exists to find, and it is systematically blind to the part of their value
this league actually pays for.

This was previously unfixable because play-by-play only covered 2024–25. It is
fixable now: pbp was backfilled to 2016 during this study, and
`decomposition.long_td_bonuses()` computes the counts.

## What should change

1. **Credit 40+ yard TDs in the scoring path** (or at minimum in `mispricing.py`).
   This is a correctness fix, not a model change, and it moves individual leverage
   figures by 3–5 percentage points for the players the engine most wants to
   identify. Highest-value item to come out of S1.
2. **Do not build a bonus-proneness feature for RB/WR/TE.** The train-data signal
   does not survive holdout.
3. **QB bonus residual is a legitimate but minor tiebreaker** — worth ~12 points a
   season, relevant only when QBs are otherwise close.
4. **The position-level bonus premium is worth encoding** in valuation, since it
   is mechanical rather than predictive.

## Limitations

- Long-TD credit assigns the receiving bonus to the receiver and the passing
  bonus to the quarterback on the same play, which matches how Sleeper pays it,
  but has not been reconciled against an actual Sleeper-scored game.
- The residual uses a straight line fit per position. Curvature in the true bonus
  curve would leak into the residual; a spline would be the natural refinement if
  anyone revisits this.
- Holdout samples are small at quarterback (n = 63). The QB result is the most
  confident direction here but the least confident magnitude.
- 2016 is the earliest season, set by NGS/pbp coverage rather than by weekly data
  (which reaches 2014).
