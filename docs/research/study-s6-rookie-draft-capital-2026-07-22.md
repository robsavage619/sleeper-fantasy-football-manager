# S6 — What draft capital is worth, priced under this league's rules

Date: 2026-07-22
Code: `src/sleeper_ffm/model/research/rookie_model.py`
Data: 2014–2022 entry classes, 1,493 skill-position players. Outcomes 2014–2024.
Bar: cleared this league's positional replacement line in any of career years 1–3.

## Why recompute what is already published

Public rookie hit rates are built for generic leagues — 12 teams, standard
scoring, "top-24" as the bar. This league is 10 teams with a QB/3RB/3WR/TE/2FLEX
lineup and heavy bonuses, so its replacement line sits somewhere else entirely.
The bar here is derived from the roster settings by
`valuation.replacement_thresholds`, not from convention.

## Two methodological notes, because both changed the answer

**Survivorship.** A drafted player who never takes a snap has no weekly rows.
Joining outcomes onto stats silently drops him, which computes hit rates over the
players who made it — the population you cannot identify on draft day. The cohort
here is anchored on the draft class, and 466 of 1,493 players who never recorded a
fantasy point are counted as misses rather than dropped.

**The replacement line must be computed within a season.** The first run of this
study pooled eleven seasons before ranking, which asks whether a player was among
the 36 best running back *seasons of the decade* rather than the 36 best backs
that year. It put first-round hit rates at 12.5%, roughly a fifth of the published
figure. That implausibility is what surfaced the bug. Corrected numbers below now
sit close to Footballguys' independently published rates, which is the reassurance
that the pipeline is sound.

## Result: three tiers, not seven rounds

Round-by-round rates have heavily overlapping intervals — rounds 1 and 2 are not
distinguishable, nor are 4 and 5, nor 6, 7 and undrafted. Collapsed to the tiers
the data actually supports (95% Wilson intervals, non-overlapping):

| Tier | n | hit rate | 95% CI |
|---|---|---|---|
| **A — rounds 1–2** | 178 | **57.9%** | 50.5–64.9% |
| **B — rounds 3–5** | 321 | **21.2%** | 17.1–26.0% |
| **C — round 6+ / undrafted** | 994 | **3.2%** | 2.3–4.5% |

The tiers are stable across eras, which is the closest thing to out-of-sample
validation available for a base-rate model:

| Tier | 2014–2019 | 2020–2022 |
|---|---|---|
| A | 55.7% (n=115) | 61.9% (n=63) |
| B | 24.2% (n=215) | 15.1% (n=106) |
| C | 3.1% (n=713) | 3.6% (n=281) |

**Within tier A, pick number adds little.** Picks 1–16 hit at 67.3% against 54.0%
for picks 17–64, and those intervals overlap. Once a player is a top-two-round
selection, precisely how early he went is weak information.

## The finding that should drive the draft

Hit rates by position, within tier A:

| Position | n | hit rate | 95% CI |
|---|---|---|---|
| **RB** | 34 | **88.2%** | 73.4–95.3% |
| WR | 81 | 56.8% | 45.9–67.0% |
| TE | 27 | 48.1% | 30.7–66.0% |
| **QB** | 36 | **38.9%** | 24.8–55.1% |

An early-round running back becomes startable here **more than twice as often as
an early-round quarterback**, and those two intervals do not overlap.

This is a statement about *this league*, not about football. It falls out of the
lineup: three starting running back slots plus two flexes against a 10-team pool
means the replacement line for backs is shallow and easy to clear, while a single
quarterback slot means only ten quarterbacks are startable at any time against 32
NFL starters. The same players in a superflex league would invert this ranking.

That is exactly why it is worth knowing. Rookie ADP is set by the consensus
dynasty market, which prices for 12-team superflex conventions. In this league
early-round running backs are the most reliable rookie asset available, and
quarterbacks the least — regardless of what the board says.

## What should change

1. **Weight rookie valuation toward tier, not round.** Seven rounds of granularity
   is false precision; three tiers is what the data supports.
2. **Apply a position adjustment inside tier A**, favouring backs and fading
   quarterbacks, sized to this league's lineup rather than to generic dynasty ADP.
3. **Treat everything from round 6 down as one undifferentiated 3% lottery.**
   Round-6 picks, round-7 picks and undrafted free agents are statistically
   identical here.

## Limitations

- "Ever startable in three years" is a binary and ignores magnitude. A player who
  clears the line once and one who is a perennial top-five asset both count as
  hits. A value-weighted version would rank tier A above where this puts it.
- The 2022 class has only three seasons of follow-up through 2024, so its
  three-year window is complete but its later development is not observed.
- Position cells inside tier A are small (27 tight ends, 34 backs). The RB-versus-QB
  gap is wide enough to survive that; finer splits would not be.
- Draft capital is taken from the nflverse ID map rather than from an audited draft
  table; a handful of undrafted players may be miscoded.
- This measures NFL draft capital, not rookie-draft position. Converting it into
  advice for a specific pick needs the rookie ADP mapping, which is not done here.
