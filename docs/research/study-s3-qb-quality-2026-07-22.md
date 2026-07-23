# S3 — Quarterback quality moves receiver efficiency, not receiver usage

Date: 2026-07-22
Code: `src/sleeper_ffm/model/research/qb_quality.py`
Data: NGS passing (CPOE) + league-scored weekly, 2016–2025. 793 receiver season-pairs.
Split: train ≤2023 pairs, holdout 2024–25 pairs

## Why this study exists

S2 reported that a quarterback change is the mildest of three disruptions for pass
catchers, measured on target share. The Q5 literature review argued that was the
wrong instrument: published tier studies find target *volume* barely moves across
quarterback tiers while points per target fall sharply. This tests that directly on
our own data.

Identification is within-player. Comparing receivers who play with good
quarterbacks against those who do not would mostly rediscover that good offenses
employ good players. Instead each receiver is paired with his own previous season,
and the question is whether the *change* in his quarterback's accuracy predicts the
*change* in his production. The receiver is his own control.

Quarterback quality is completion percentage over expectation, which is already
adjusted for throw difficulty.

## Result: the literature was right, and S2 measured the one channel with no effect

| Outcome | WR (n=601) | TE (n=192) |
|---|---|---|
| **Points per target** | **r = +0.343** | **r = +0.235** |
| Targets per game | r = −0.088 | r = +0.089 |

Quarterback accuracy has a substantial relationship with how much a receiver scores
*per opportunity* and essentially none with how many opportunities he gets. A
better quarterback does not throw to his receiver more often. He makes each throw
worth more.

This replicates out of sample and gets stronger:

| Position | train (≤2023) | holdout (2024–25) |
|---|---|---|
| WR | +0.335 (n=460) | **+0.390** (n=141) |
| TE | +0.206 (n=137) | **+0.327** (n=55) |

### Magnitude

A one-standard-deviation swing in quarterback CPOE is worth:

- **0.93 fantasy points per game to a receiver** — roughly 26 points over this
  league's 28-game season
- **0.48 points per game to a tight end** — roughly 13 points

That is among the largest effects measured in this research program, and larger
than the entire validated quarterback bonus-proneness edge from S1 (12 points).

## What this corrects

S2's conclusion that quarterback changes are the mildest disruption is true of
role and false of value. Target share was the wrong measure, and the error was
systematic rather than incidental: usage is precisely the channel through which
quarterback quality does *not* operate, so a usage-based study is structurally
guaranteed to find nothing.

The general lesson for the rest of this program: when the question is about value,
do not answer it with a usage metric.

## What should change

1. **Add a quarterback-quality term to pass-catcher projections.** The effect is
   large, replicated out of sample, and currently absent from the engine — the
   forecast has no notion of who is throwing the ball.
2. **Apply it to efficiency, not volume.** Scaling projected targets by quarterback
   quality would be wrong in a way this study specifically rules out. The
   adjustment belongs on points per target.
3. **Use it when valuing a receiver whose quarterback situation is changing** —
   which S2 established is over half of returning player-seasons.

## Limitations

- **This is association, not a clean causal estimate.** The within-player design
  controls for receiver talent but not for everything else that moves when a
  quarterback improves: offensive line play, scheme, pace, receiving corps around
  him. A quarterback's CPOE rising alongside a generally improving offense would
  produce this result without the quarterback being the cause. Treat the effect
  size as an upper bound on the quarterback's own contribution.
- CPOE is an accuracy measure and misses arm strength, depth of target and
  scrambling, so it is a partial proxy for quarterback quality.
- Team-season primary quarterback is modal by games started, so receivers on teams
  that split a season between two quarterbacks are assigned to one of them.
- Tight end samples are thin (55 holdout pairs).
