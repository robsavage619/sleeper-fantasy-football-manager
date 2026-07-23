# S2 — Does production follow the player or the situation?

Date: 2026-07-22
Code: `src/sleeper_ffm/model/research/situation_changes.py`
Data: player-season context table, 2015–2025, ≥8 games at both ends
Split: train ≤2023, holdout 2024–25

## Question

When a player changes teams, does he take his role with him, or does he inherit
whatever the new offense hands him? Players who stay put are the control group.
If prior usage predicts current usage as well for movers as for stayers, the role
travels; if the relationship decays, the situation is doing the work.

Three disruptions are tested separately, because they are not the same event: a
new team, a new play-caller, a new primary quarterback. The engine is currently
blind to all three, despite them affecting 28%, 42% and 53% of returning
player-seasons respectively.

## Headline

**It depends entirely on position, and the split is sharp.**

Target-share carryover (Pearson r, prior season → current season) after a team change:

| Position | moved | moved, corrected¹ | stayed | corrected gap |
|---|---|---|---|---|
| RB | 0.353 | 0.416 | 0.695 | **−0.279** |
| TE | 0.604 | 0.678 | 0.761 | −0.083 |
| WR | 0.660 | 0.703 | 0.781 | −0.078 |

¹ Movers have measurably narrower prior-usage spread than stayers (RB sd 0.035 vs
0.043), so part of the raw gap is range restriction rather than situation. The
corrected column applies the Thorndike case-2 correction. The RB effect survives
it; most of the WR and TE effect does not.

**A running back's role does not travel. A receiver's does.** For a back who
changes teams, prior usage explains about 17% of his new usage; for one who stays,
48%. The role is a property of the offense, assigned on arrival, not a possession
the player carries with him.

Out of sample the RB result holds and the WR result disappears entirely:

| Position | train gap | holdout gap | holdout n (moved) |
|---|---|---|---|
| RB | −0.401 | −0.302 | 31 |
| WR | −0.124 | −0.006 | 56 |

So the honest statement is narrower and stronger than "situation matters": it
matters at running back specifically, and receivers should be treated as carrying
their role essentially intact.

### The age confound is real and does not explain the result

Players who change teams are substantially older than those who stay — 28.2 vs
25.8 for backs, 28.6 vs 26.2 for receivers. A 2.4-year gap is enough that "moved
backs decline" could simply be "old backs decline". It is not:

| Age band | moved | stayed | gap | n moved |
|---|---|---|---|---|
| 21–25 | 0.621 | 0.661 | −0.040 | 10 |
| 25–28 | 0.328 | 0.744 | **−0.416** | 67 |
| 28–34 | 0.335 | 0.703 | **−0.368** | 59 |

Within age bands the gap is larger than the pooled estimate, not smaller. The
situation effect is real and independent of aging.

The 21–25 row hints that young backs keep their roles when they move while older
ones do not — which would fit the obvious story (a young back is traded because
someone wants him, an older one because his team is done with him). With ten
movers it is not a finding, only a well-motivated question for a later study.

### Coaching changes cost running backs almost as much as moving teams

Same measurement, holding the player on his team and changing the play-caller:

| Position | new coach | same coach | gap |
|---|---|---|---|
| RB | 0.509 | 0.725 | −0.216 |
| TE | 0.664 | 0.769 | −0.105 |
| WR | 0.701 | 0.796 | −0.095 |

A back does not have to move to lose his role — a new play-caller is nearly as
disruptive as a new team. Quarterback changes are the mildest of the three
disruptions for pass catchers (WR gap −0.074), which is mildly surprising and
worth its own study.

## The null worth acting on: vacated opportunity does not transfer

The standard fantasy heuristic says a team that lost 150 targets has 150 targets
waiting for whoever arrives. Correlation between the share of team targets vacated
before a season and the incoming mover's actual usage:

| Position | n | r vs prior usage | r vs vacated share |
|---|---|---|---|
| WR | 245 | 0.660 | **0.181** |
| TE | 106 | 0.604 | 0.058 |
| RB | 141 | 0.353 | 0.047 |

Vacated opportunity explains about 3% of an incoming receiver's usage and
essentially none of a back's or a tight end's. A player's own track record is
three to seven times more informative than the hole he is signed into. Chasing
vacated targets is close to noise.

Note the tension with the finding above: a back's prior usage is itself weak
(r = 0.35), and the vacated opportunity that might have replaced it as a signal is
weaker still (r = 0.05). **Incoming running backs are genuinely hard to forecast
from either direction** — which is itself the actionable result, since the market
prices them as though their track record carries.

#### The mixture explanation, tested and rejected

The table above covers players who *arrived*. A reasonable objection, raised by
the Q3 literature review, is that this measures the wrong group: opportunity
vacated by a departing star may go to the incumbent promoted behind him rather
than to an outside signing, in which case the near-null would be an artifact of
pooling two different mechanisms.

It is not. For incumbents the right question is whether vacated opportunity
predicts their usage *gain*, and it does not:

| Position | incumbents (n) | r, vacated → usage gain | arrivals, r → usage level |
|---|---|---|---|
| WR | 799 | +0.062 | +0.181 |
| RB | 488 | +0.031 | +0.047 |
| TE | 425 | +0.121 | +0.058 |

Incumbents are *weaker* than arrivals, not stronger. The null holds on both sides
of the split, which makes it considerably more robust than the original single
measurement — a named alternative explanation was tested and did not survive.

## What should change

1. **Discount a running back's usage history when he changes team or coach.**
   This is the single largest situation effect measured, it survives correction
   and holdout, and the engine currently applies no discount at all.
2. **Do not discount receivers.** The apparent penalty does not replicate.
3. **Do not build a vacated-opportunity feature** as a usage predictor. It is a
   near-null and would add confident-looking noise to exactly the calls
   (post-move backs) where the engine is already weakest.
4. **Widen the uncertainty band on moved running backs** rather than shifting
   their point estimate. The finding is that they are unpredictable, not that
   they are worse.

## Limitations

- Usage share is measured as a per-game mean rather than a team-total ratio, so a
  player who misses time inside a season is weighted by games played rather than
  by team snaps.
- The control group is not clean: a "stayer" whose team changed coordinators
  without changing head coach counts as stable here, because the context table
  tracks head coach only. Real play-caller churn is undercounted, which if
  anything biases the measured coaching effect downward.
- Holdout samples are thin (31 moved backs, 56 moved receivers). Direction is
  well supported; magnitudes are not precise.
- Age is controlled by stratification rather than by a model, so residual
  within-band age differences are not removed.
