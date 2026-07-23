# S4 — Archetype does not change decline. It changes survival.

Date: 2026-07-22
Code: `src/sleeper_ffm/model/research/archetypes.py`
Data: 3,559 player-seasons, 2014–2025, ≥8 games, ages 22–33.

## Question

The engine's age curves are league-wide per position — every running back declines
on the same schedule. The code documents this as the "next real improvement", and
Q6 found no published archetype-conditional aging curves anywhere reachable, so
this builds rather than reproduces.

Archetypes are split at each position's own median, so the groups are balanced by
construction and the cut point is not chosen to produce a result:

- **Running backs** on receiving share of touches: `grinder` vs `receiving_back`
- **Receivers and tight ends** on yards per reception: `possession` vs `field_stretcher`

## The design problem that had to be solved first

The initial cross-sectional run said older players *outscore* younger ones at five
of six archetypes — running back grinders by 14.8%, possession receivers by 19.2%.
That is not aging, it is survivorship. A 31-year-old still starting was selected on
having aged well; the peers who declined left the league and are absent from the
sample. Cross-sectional age comparisons cannot measure aging in a population that
is culled on performance.

Two designs replace it, and together they cover the population:

1. **Within-player change** — each player differenced against himself, so his own
   quality drops out. Measures decline *conditional on still playing*.
2. **Attrition** — the probability that a qualifying season is not followed by
   another. This is Harstad's mortality-table frame, which Q6 identified as the
   methodologically superior approach, and it captures exactly the players design
   1 must drop.

## Result 1: decline is a null

Within-player change in points per game, by archetype and age band:

| Position | Archetype | 22–24 | 25–27 | 28+ |
|---|---|---|---|---|
| RB | grinder | +0.30 | −0.77 | −1.75 |
| RB | receiving_back | +0.48 | −0.86 | −1.31 |
| WR | field_stretcher | +0.09 | −0.72 | −1.83 |
| WR | possession | +1.28 | −0.26 | −1.08 |
| TE | field_stretcher | +0.91 | −0.56 | −0.48 |
| TE | possession | +0.74 | −0.01 | −0.64 |

The curves are sensible — improvement through the early twenties, decline
accelerating after 27 — but archetype does not separate them. Of nine
position-by-band comparisons, **one** is statistically significant (young
possession receivers improving faster than young field-stretchers, +1.19 ± 0.76).
With nine tests at the 5% level, roughly one false positive is the expectation. It
marginally survives a Bonferroni correction and is recorded as a hypothesis, not a
finding.

**Splitting the engine's age curves by archetype would add noise, not signal.**

## Result 2: attrition is not a null

The same archetypes, asked instead how likely a player is to stop being startable
at all:

| Position | Archetype | 22–24 | 25–27 | 28+ |
|---|---|---|---|---|
| RB | grinder | 29.3% | 28.5% | 35.0% |
| RB | **receiving_back** | 22.8% | **41.1%** | **56.0%** |
| WR | field_stretcher | 23.0% | 20.9% | 34.2% |
| WR | **possession** | 28.7% | **33.3%** | 43.2% |
| TE | field_stretcher | 20.8% | 25.9% | 25.4% |
| TE | **possession** | 27.5% | 32.5% | **43.8%** |

Four of nine comparisons are significant against an expectation of 0.45 by chance:

- **RB 25–27**: receiving backs +12.7pp ± 9.9
- **RB 28+**: receiving backs +21.0pp ± 13.0
- **WR 25–27**: possession +12.4pp ± 7.7
- **TE 28+**: possession +18.4pp ± 11.4

The running back result is the strongest and the most contrarian. Conventional
dynasty wisdom holds that pass-catching backs age *better* because receiving work
is less punishing than carries. In this sample the opposite holds after 25:
receiving backs are safer than grinders while young (22.8% vs 29.3%) and
substantially more likely to disappear once past it, ending at 56% annual attrition
after 28 against a grinder's 35%.

## What this means

The two results together give a precise instruction, which is more useful than
either alone: **archetype belongs in the risk model, not in the age curve.**

How much a player declines given that he is still playing does not depend on his
archetype. Whether he is still playing does. An engine that models only the former
— which is what a mean age curve does — will systematically misprice the latter,
and it will misprice it worst for exactly the profiles dynasty managers hold onto:
receiving backs and possession receivers past 25.

## What should change

1. **Leave the position-level age curves alone.** The documented "next real
   improvement" turns out not to be an improvement.
2. **Add archetype-conditional attrition to dynasty valuation** as a survival
   probability, separate from the decline curve.
3. **Fade receiving backs past 25 harder than the market does**, since the
   conventional view has the sign backwards on this measure.

## Limitations

- **The running back split is a ratio and may not mean what its name says.** A back
  with 20 carries and 15 targets is labelled `receiving_back` identically to one
  with 200 carries and 80 targets, so the group mixes genuine receiving specialists
  with low-volume committee backs who are easily replaced. That alone could drive
  the attrition result, and it is the first thing a follow-up should separate.
- Attrition here means "no qualifying season next year", which conflates injury,
  losing a job, and retirement. Those have different implications for a dynasty
  roster and are not separated.
- The ≥8 game qualifier means a player who plays 6 games counts as attrition even
  if he is healthy and rostered the following year.
- Median splits produce two groups per position; a three-way split would describe
  real roles better but halves the cells.
- Ages come from the ID map birthdate and are rounded to whole years.
