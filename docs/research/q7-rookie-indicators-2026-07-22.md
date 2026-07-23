# Q7 — Rookie and early-career breakout indicators

Research date: 2026-07-22. Question: what is the relative predictive weight of NFL draft capital
versus college production (dominator rating, breakout age, market share, per-route efficiency)
versus athleticism (combine testing), for forecasting NFL fantasy success, by position?

Scope note: everything below is public-analyst work and industry data, not peer-reviewed research.
No allowlisted academic source was found that models fantasy points specifically (see "What could
not be sourced" at the end). Treat effect sizes as directional, not as calibrated coefficients.

---

## 1. The headline finding: draft capital dominates, and it dominates by a lot

Every independent source found agrees on the ordering. Draft capital is the single strongest
predictor of early-career fantasy production at every skill position, and the gap between it and
the next-best variable is large.

Ryan Heath, who builds the Fantasy Points rookie RB model back to the 2015 draft class, states it
flatly: the model's goal is to predict "the average PPR fantasy points of a player's best two
seasons out of their first three in the NFL," and "Draft capital (the pick slot at which a player
is selected in the real NFL Draft) is by far the most predictive variable to accomplish this goal."
(Ryan Heath, Fantasy Points, "Ryan Heath's 2026 Rookie RB Rankings",
https://www.fantasypoints.com/nfl/articles/2026/ryan-heaths-rookie-rb-rankings)

The methodological point that matters most for our engine comes from a data scientist writing as
DSnasty_ff, who ran the correct test — not "does metric X correlate with NFL production" but "does
metric X add predictive power *on top of* draft capital." His framing: "if we move that RB up our
rankings both because they have first-round draft capital AND a strong 40 time, are we actually
double-counting the strong 40 time?" (DSnasty_ff, "The Most (and Least) Meaningful Stats for
Evaluating RB Prospects", https://dsnastyff.substack.com/p/the-most-and-least-meaningful-stats)

This is the correct null hypothesis for any rookie model. Most published "predictive metrics" are
predictive only because NFL teams already price them into draft position.

### Hit rates by draft round — the hard numbers

Jason Wood at Footballguys computed 10-year (2016–2025) rookie-season hit rates for every skill
position. These are the most concrete numbers in this corpus.

**Wide receiver** (323 drafted, 2016–2025). Threshold is top-48 rookie-year PPR finish.
(Jason Wood, Footballguys, "Draft Capital Matters: Rookie Wide Receivers",
https://www.footballguys.com/article/2026-draft-capital-matters-rookie-wide-receivers)

| Round | N | Top-48 | Top-36 | Top-24 | Top-12 |
|---|---|---|---|---|---|
| 1 | 43 | 55.8% | 46.5% | 27.9% | 11.6% |
| 2 | 50 | 30.0% | 22.0% | 10.0% | 2.0% |
| 3 | 46 | 10.9% | 4.3% | 0.0% | 0.0% |
| 4 | 43 | 2.3% | 2.3% | 2.3% | 0.0% |
| 5 | 40 | 7.5% | 7.5% | 5.0% | 2.5% |
| 6 | 53 | 0.0% | 0.0% | 0.0% | 0.0% |
| 7 | 48 | 0.0% | 0.0% | 0.0% | 0.0% |
| All | 323 | 14.9% | 11.5% | 6.2% | 2.2% |

Collapsed by draft day: Day 1 55.8% top-48, Day 2 (96 players) 20.8%, Day 3 (184 players) 2.2%.
Of the 49 fantasy-relevant rookie WR seasons in the decade, 24 (49%) were first-rounders, 15 (31%)
second, 5 (10%) third, and only 5 total came from rounds 4–7 plus one UDFA (Keelan Cole). Zero
sixth- or seventh-round WRs produced a top-48 rookie season in ten years.

Note the round-5 anomaly (7.5% > round 4's 2.3% and round 3's 10.9% on some thresholds). That is
three players — Puka Nacua, Tyreek Hill, Darius Slayton — in a 40-player cell. It is noise, not a
real non-monotonicity, and any model that smooths draft capital should not fit it.

**Tight end** (141 drafted, 2016–2025). Threshold is top-24 rookie-year finish.
(Jason Wood, Footballguys, "Draft Capital Matters: Rookie Tight Ends",
https://www.footballguys.com/article/2026-draft-capital-matters-rookie-tight-ends)

| Round | N | Top-24 | Top-12 |
|---|---|---|---|
| 1 | 11 | 81.8% | 54.5% |
| 2 | 19 | 21.1% | 5.3% |
| 3 | 24 | 8.3% | 4.2% |
| 4 | 30 | 6.7% | 0.0% |
| 5 | 23 | 8.7% | 0.0% |
| 6 | 16 | 0.0% | 0.0% |
| 7 | 18 | 0.0% | 0.0% |
| All | 141 | 13.5% | 5.7% |

TE is the most extreme position in the corpus. Nine of eleven first-round TEs since 2016 hit top-24
as rookies and six of eleven hit top-12. Off Day 1, the position is close to worthless in year one:
Day 2 is 14.0% top-24, Day 3 is 4.6% top-24 and 0.0% top-12. Sample size on round 1 is only 11, so
the 81.8% has a wide interval — but even the pessimistic end of that interval clears every other
round by a mile.

**Quarterback** (118 drafted, 2016–2025). Threshold is top-24 (Superflex-relevant).
(Jason Wood, Footballguys, "Draft Capital Matters: Rookie Quarterbacks",
https://www.footballguys.com/article/2026-draft-capital-matters-quarterbacks)

| Round | N | Top-24 | Top-12 |
|---|---|---|---|
| 1 | 35 | 45.7% | 14.3% |
| 2 | 7 | 14.3% | 0.0% |
| 3 | 14 | 0.0% | 0.0% |
| 4 | 14 | 7.1% | 7.1% |
| 5 | 14 | 0.0% | 0.0% |
| 6 | 19 | 5.3% | 0.0% |
| 7 | 15 | 0.0% | 0.0% |
| All | 118 | 16.1% | 5.1% |

16 of 19 fantasy-relevant rookie QB seasons (84%) came from round 1. Dak Prescott (round 4, 2016)
is the only non-first-rounder to finish top-12 as a rookie in the decade, and he only played because
Tony Romo fractured a vertebra in the preseason. The round-4 7.1% cell is literally Prescott.

**Running back**: the equivalent Footballguys RB piece was scheduled for 2026-07-24 and is not yet
published as of the research date (the article series index lists "RBs (7/24)" without a link). No
comparable round-by-round RB hit-rate table was found on an allowlisted domain. Flagged as a gap.

---

## 2. What college production adds *beyond* draft capital

This is the part that matters, because draft capital is knowable and free. The only useful metrics
are the ones with residual signal after you condition on it.

### Wide receiver: breakout age and market share survive; almost nothing else does

DSnasty_ff's WR study (https://dsnastyff.substack.com/p/the-most-and-least-meaningful-stats-ce8)
partitions metrics into three buckets after conditioning on draft capital:

*Adds significant predictive value beyond draft capital:*
- **Breakout age.** "Of the metrics I looked at, it was the single most predictive stat outside of
  draft capital."
- **Share of team receiving yards.** Adds value on top of *both* draft capital and breakout age.
  His explanation is worth encoding directly: breakout age is a threshold statistic — it records
  only *that* a player crossed 20% dominator, not by how much. Raw yardage market share carries the
  magnitude information the threshold discards. So the two are complements, not substitutes.

*Tiebreaker only, and all three point the WRONG way:*
- Share of team receiving TDs — higher is slightly *worse*
- Catch rate — higher is slightly *worse*
- Yards after catch per reception — higher is slightly *worse*

His read: "either NFL teams are overvaluing these metrics slightly, or that these metrics are more
important for actual football than they are for fantasy football." A WR who earned first-round
capital *without* padded TD share is a better fantasy bet than one who earned it with.

*Ignore entirely once draft capital is known:*
- Every NFL Combine metric ("Every metric from the NFL Combine can be safely ignored once you factor
  in draft capital for WRs")
- Slot vs. perimeter alignment rate
- College level of competition
- Age
- PFF pass-blocking grade
- Contested-catch rate
- Average depth of target

The aDOT and contested-catch nulls are notable because both are heavily used in public dynasty
discourse.

### The definitions, so we implement them the same way everyone else does

PlayerProfiler's glossary is the canonical public definition and should be what our engine matches
(PlayerProfiler, "Advanced Stats Glossary of Terms", https://www.playerprofiler.com/terms-glossary/):

- **College Dominator Rating** — a player's percentage of his team's offensive production. For WR
  and TE it is the share of team receiving production (yards and TDs combined). "A 35+% dominator
  indicates that a wide receiver has the potential to be a team's No. [1]. Less than 20% is a red
  flag." The metric traces to Frank DuPont's book *Game Plan*.
- **Breakout Age** — "the age at the beginning of the college football season when they first
  posted a Dominator Rating at or above 20%" for WRs. For **TE and RB the threshold is 15%**, not
  20%. For QB, breakout is defined by first season with QBR ≥ 50 at ≥20 action plays per team game.
  The concept originated with Frank DuPont and Shawn Siegele at RotoViz.

Breakout age is measured at *season start*, and the TE/RB threshold difference is the kind of detail
that silently corrupts a re-implementation.

### The empirical shape of a WR breakout profile

Apex Fantasy Leagues profiled every rookie WR breakout and reports the composite:
"22.1 years old, drafted 39th overall, 204 lbs, with a 33.9% peak college dominator and a college
breakout age of 19.8. Roughly 72% of breakouts forewent their senior year to enter the draft early."
And: "78% of breakouts posted a peak college dominator rating ... above 30%. Players below that line
can still hit, but they're the exceptions, not the rule."
(Apex Fantasy Leagues, "What Does a Rookie Wide Receiver Breakout Look Like?",
https://apexfantasyleagues.com/what-does-a-rookie-wide-receiver-breakout-look-like/)

Note the domain is not on the allowlist; it surfaced with full text in search results rather than by
scrape. Treat these three numbers as lower-confidence than the Footballguys and Substack figures.
The screening filter they apply is: age ≤ 22, peak dominator > 30%, breakout age < 20.5.

### The three-factor public consensus model

The most widely circulated public WR framework is Elite Drafters' — draft capital, yards per route
run, breakout age. "Built on draft capital, yards per route run (YPRR), and breakout age, the model
has shaped wide receiver evaluation ... since early 2021." On YPRR: "YPRR from the season before a
player is drafted into the NFL is often the most relevant and best predictor, but looking at the
change in YPRR over time can be just as important," and a YPRR of 3.0 or higher is treated as elite.
Their production model uses *career* YPRR rather than final-season YPRR, which materially reorders
players (the article names Emeka Egbuka and Luther Burden as beneficiaries).
(Elite Drafters / Jack Reinhart, "Predictive Rookie Receiver Metrics",
https://elitedrafters.substack.com/p/predictive-rookie-receiver-metrics)

Conflict to be aware of: Elite Drafters treats YPRR as a headline input; DSnasty_ff did not test
YPRR for WRs (he tested it for RBs, where it was the strongest non-draft-capital signal). Neither
directly contradicts the other, but our engine should test WR YPRR's incremental-over-draft-capital
value itself rather than assuming it.

### Running back: receiving usage and yardage creation, not rushing efficiency

DSnasty_ff's RB study (https://dsnastyff.substack.com/p/the-most-and-least-meaningful-stats):

*Adds significant predictive value beyond draft capital:*
- **Yards per route run.** "Outside of draft capital, this was the single strongest predictive stat
  that I measured." For a running back.
- **Share of offense**, defined as total touches divided by total offensive snaps — the *combination*
  of rush share and target share, not either alone.

*Tiebreakers:*
- **BMI** — the only combine-derived quantity with residual signal, and only as height/weight
  composite; "height and weight by themselves didn't add much." Prefer the shorter/heavier back.
- **Age — inverted.** "Being OLDER adds a little bit of positive signal for higher fantasy output."
  He attributes this to older backs being NFL-ready sooner, and explicitly scopes it to redraft:
  "In dynasty there's obviously additional value to drafting younger players, so this one is really
  more for redraft."
- **College level of competition — inverted.** "RBs with LOWER college level of competition ...
  actually were predicted for better fantasy output. It's possible the NFL slightly overvalues
  players from big college programs, and undervalues players from smaller schools."
- Yards after contact per rush attempt

*Ignore:*
- "Almost everything from the NFL Combine": 40-yard dash, speed score, 20-yard shuttle, three-cone,
  bench press, broad jump
- Yards per rush attempt
- Touchdowns, including share of team TDs
- PFF elusive rating

Ryan Heath's Fantasy Points model converges on the same shape from a different direction. After
draft capital, his model uses exactly two variables:

1. **Yards After per Game (YA/G)** — PFF-charted yards after contact (rushing) plus yards after
   catch (receiving), divided by games. "An all-in-one RB metric that combines volume consolidation
   and yardage creation, while also rewarding receiving." He found it "slightly more predictive"
   than yards from scrimmage per team play or missed tackles forced. Critically, he uses the
   player's **2nd-best season**, not his best: "for the most part, a great 2nd-best season signals a
   great best season, so using the 2nd-best season gives the model some information on both." He
   also strength-of-schedule adjusts it.
2. **Final-season targets per route run (TPRR).** Chosen over YPRR, receiving yards market share,
   yards per target and yards per team pass attempt because it "was both the most predictive of the
   bunch *and* wasn't too correlated with YA/G."

(Ryan Heath, Fantasy Points, https://www.fantasypoints.com/nfl/articles/2026/ryan-heaths-rookie-rb-rankings)

Two more Heath findings that bear directly on model design:
- **Age is not a useful RB adjustment.** "Chronological age doesn't seem to matter as much at RB;
  unlike at WR and TE, my model wasn't made any more predictive by adjusting for age, so I don't do
  it directly." This *corroborates* DSnasty_ff's inverted-age result — both say the standard
  younger-is-better prior does not hold for RB prospects.
- **One-hit wonders underperform their capital.** "One-hit wonders have horrendous track records
  relative to their draft capital." This is the justification for the 2nd-best-season construction.
- **Landing spot matters far more for RB than WR/TE**, "since RB is an inherently opportunity-driven
  position, and there's rarely more than one of them on the field at any given time."

---

## 3. Athleticism: mostly already priced in, with one live disagreement

There is a genuine conflict in the sourced material here, and per house rules I am naming it rather
than averaging it.

**Position A — combine testing adds nothing once you know draft capital.** DSnasty_ff for both RB
and WR: for RBs, "none of them add any predictive power to draft capital"; for WRs, "Every metric
from the NFL Combine can be safely ignored once you factor in draft capital." His caveat is
important and is *not* a hedge — it is the mechanism: "it just means NFL teams are good at
evaluating the Combine results, so more athletic RBs are getting the higher draft capital they
deserve." Athleticism is real; it is just not *incremental information* to us.

**Position B — combine testing has position-specific predictive content.** Raymond Summerlin at
Sharp Football Analysis argues the answer "depends almost entirely on the position": WR and TE have
"meaningful correlations with NFL production," RB does not respond to straight-line speed, and QB
combine performance "is almost entirely irrelevant." His specific claims:
- RB: burst score (broad + vertical), 10-yard split, agility score (shuttle + three-cone), and
  weight-adjusted speed beat raw 40 time. "A 215-pound back running a 4.48 is producing a very
  different result than a 185-pound back running the same time."
- WR: the three-cone is the best combine proxy for route-running fluidity; "Research has shown that
  the three cone correlates strongly with separation rate and, by extension, target volume and
  production." The 40 functions as a threshold check, with sub-4.50 as the cutoff below which
  straight-line speed stops being a limiter.
- TE: "the position where Combine athleticism is most determinative of fantasy upside," because
  many TEs are drafted as blockers and testing separates the ones with a receiving ceiling. Vertical
  jump is a catch-radius and red-zone proxy.
- Bench press: no relationship to skill-position production at any position.
- RAS (Relative Athletic Score, Kent Lee Platte, https://ras.football/) as the summary filter: >9.0
  elite, 7.0–9.0 good, 5.0–7.0 average, <5.0 raises the bar for everything else.

(Raymond Summerlin, Sharp Football Analysis, "What NFL Combine Results Actually Mean for Fantasy
Football Drafts", https://www.sharpfootballanalysis.com/fantasy/what-nfl-combine-results-mean-for-fantasy/)

**How to resolve the conflict.** Note that Summerlin never claims incremental value over draft
capital — he reports raw correlations with production. DSnasty_ff tests the conditional question.
Those are different tests, and both can be true simultaneously: three-cone can correlate with
separation rate *and* add nothing once you know the player went 12th overall. Summerlin's own
framing supports this reading — he calls the combine "a filter" and says "Athletic profile and
opportunity are both required, and the Combine only tells you about one of them."

A partial reconciliation comes from Heath, who uses athleticism only "at the polar extremes, where
it provides the most signal", citing his own Fantasy Points combine study
(https://www.fantasypoints.com/nfl/articles/2025/nfl-combine-what-matters-for-fantasy). He also
notes a specific RB speed-score effect that *does* survive conditioning: a 4.9-band speed score
"places him in a bucket associated with fewer early-career fantasy points, whether we control for
draft capital or not." That is a tail effect, not a linear one — bad athleticism is disqualifying
in a way that good athleticism is not confirming.

Heath's blunt aside on why athleticism gets double-counted in ADP is worth carrying into our
mispricing logic: "teams and the Draft media alike double-count athleticism all the time."

**Working synthesis, labelled as such**: athleticism enters as a *floor filter with tail asymmetry*,
not a linear term. Below-threshold testing (roughly RAS < 5, or a bottom-decile weight-adjusted
speed score) is real negative information; above-threshold testing is already in the draft slot.
This is a synthesis of Heath and DSnasty_ff, not a claim either one made in this form — **unsourced
prior, verify empirically in Phase 2**.

---

## 4. Position-by-position summary of predictive weight

| Position | 1st | 2nd | 3rd | Explicit nulls |
|---|---|---|---|---|
| QB | Draft capital (round 1 or nothing: 84% of relevant rookie seasons) | Rushing volume projection | — | Combine testing "almost entirely irrelevant" |
| RB | Draft capital | Yards-after-per-game (2nd-best season, SOS-adj) / share of offense | Final-season TPRR or YPRR | Combine (except BMI and tail speed score), YPC, TDs, PFF elusive rating, age, strength of competition |
| WR | Draft capital | Breakout age | Team receiving-yard market share (magnitude beyond the 20% threshold) | Entire combine, aDOT, contested-catch rate, slot rate, catch rate, TD share, YAC/rec, age, competition |
| TE | Draft capital, near-deterministically (round 1: 81.8% top-24 / 54.5% top-12; everything else ≤21%) | Athletic profile relative to size (Sharp, unconditional) | Production profile (Elite Drafters ranks Eli Stowers's production profile above Kenyon Sadiq's 4.39-driven athletic profile) | Bench press |

The TE row is where the corpus is thinnest on *conditional* evidence — no one ran the
DSnasty-style incremental test for tight ends. **Unsourced prior, verify empirically in Phase 2:**
that TE breakout age at the 15% dominator threshold behaves like WR breakout age.

---

## 5. Second-order findings worth encoding

**Early declaration is a strong marker.** 72% of rookie WR breakouts skipped their senior season
(Apex Fantasy Leagues, link above). This is mechanically entangled with breakout age and draft
capital and is probably not independent signal, but it is a cheap feature.

**Weight has a floor at WR.** The Apex profile flags Tutu Atwell as checking both production boxes
while being "55.6 lbs. lighter than the average breakout." Heath's RB version: "We're ultimately
looking for players who can sustain a fantasy-relevant workload; those usually aren't the guys who
weigh 175 pounds."

**Threshold metrics discard magnitude.** DSnasty_ff's cleanest structural insight, restated because
it generalizes past breakout age: any binarized feature (breakout age, "hit 30% dominator",
"sub-4.50 40") throws away the distance past the threshold, and the raw continuous version often
carries residual signal alongside the binary. Encode both.

**Beware of metrics selected post hoc on a carved sample.** Jakob Sanderson's warning is the best
statement of the failure mode in this literature: "whenever you carve off the sample of available
data into one metric, you substantially decrease the chance that your sample is reliably predictive,
rather than merely descriptive of past outcomes," and "almost all the indicators you look at are
going to be positively correlated with one another, because each is a stream flowing from the river
of production."
(Jakob Sanderson, "2026 Wide Receiver Class Pre-Draft Rankings and Analysis",
https://jakobsanderson.substack.com/p/2026-wide-receiver-class-pre-draft)

**Rookie TE production has structurally shifted.** Historical rookie TE finishes were terrible
(Gonzalez TE19, Gates TE20, Witten TE23, Graham TE23, Sharpe TE34), but Sam LaPorta (2023) and
Brock Bowers (2024) both finished as the overall TE1 as rookies, and 2025 produced four top-16
rookie TEs (Fannin TE8, Warren TE9, Loveland TE12, Gadsden TE16). Any model fit on pre-2023 rookie
TE data will systematically under-project the position (Footballguys TE article, link above).

---

## Hypotheses for OUR league

Format: 10-team, full PPR, heavy volume and big-play bonuses, 4-round rookie draft, 3 taxi slots.
Each hypothesis is written as something Phase 2 can test on our own data.

**H7.1 — Rookie-pick value should be an almost pure function of NFL draft capital, and our engine
should say so loudly.** The Footballguys tables give hit rates that are near-deterministic at the
extremes. In a 10-team league the fantasy-relevance bar is *easier* than the top-48 WR / top-24 TE
thresholds those tables use (we start fewer players from a smaller pool), so every hit rate above
should be treated as a conservative floor for us. Expected direction: our own rookie-pick outcome
data will show an even steeper Day-1-vs-Day-3 gap than the public numbers, because a 10-team league
concentrates the useful players.

**H7.2 — Full PPR plus reception/volume bonuses should raise the weight on target-earning metrics
and lower it on efficiency metrics, relative to the public models.** Both DSnasty_ff (WR: market
share good, catch rate and YAC/rec inverted) and Heath (RB: TPRR chosen over YPRR precisely because
it isolates *target earning*) already point this way in half-PPR-ish framings. In our scoring,
targets-per-route-run should outrank yards-per-route-run for both RB and WR, because our scoring
pays for the reception itself. Testable: refit our rookie score with TPRR swapped for YPRR and
compare on our own historical rookie outcomes.

**H7.3 — Our big-play bonuses should partially rehabilitate two metrics the public research nulls
out: aDOT and YAC per reception.** DSnasty_ff found aDOT irrelevant and YAC/rec *inverted* for
fantasy production — but he was scoring standard fantasy points, where a 40-yard catch is worth 4
points and not 4-plus-a-bonus. Heavy big-play bonuses change the payoff function. This is the single
most league-specific hypothesis in this document and the one most likely to produce a genuine edge
if it holds. **Unsourced prior — verify empirically in Phase 2.**

**H7.4 — With only 3 taxi slots and 4 rounds, rounds 3 and 4 of our rookie draft are almost entirely
dead capital at WR and TE, and should be traded.** Rounds 3–4 of a 10-team rookie draft correspond
roughly to NFL Day 3 picks and late Day 2. Public hit rates for that band: WR Day 3 is 2.2% top-48;
TE Day 3 is 4.6% top-24 and 0.0% top-12; WR rounds 6–7 are literally 0-for-101 over a decade. Our
engine should price our own late rookie picks near zero and be aggressive about packaging them into
future firsts or into proven players. The taxi constraint sharpens this: 3 slots means we can only
warehouse three lottery tickets, so the marginal fourth is worse than worthless — it costs a roster
spot.

**H7.5 — Prefer the older, receiving-capable RB and the younger, early-breakout WR.** This is the
one place the position-specific findings genuinely diverge, and blending them would be a mistake.
Heath: RB models are "not made any more predictive by adjusting for age." DSnasty_ff: older RBs
carry slightly *positive* signal for output, though dynasty adds an offsetting longevity premium.
Versus WR, where breakout age is the strongest non-capital predictor and the breakout composite is
19.8 years. Our engine's age curve should therefore be position-conditional at the rookie stage, not
a single global age term. This connects directly to Q6 and should be resolved jointly with it.

**H7.6 — Athleticism should enter our rookie model as a one-sided penalty, never a bonus.** Given
that draft capital already prices athleticism (DSnasty_ff's mechanism) and that the only surviving
effect Heath reports is a *negative* tail (low speed score depresses output "whether we control for
draft capital or not"), the correct functional form is a penalty below a threshold and a flat zero
above it. If our current implementation has a linear or monotone-increasing athleticism term, it is
double-counting exactly the way Heath describes the market doing. Concrete Phase 2 test: fit rookie
outcomes with (a) linear RAS, (b) RAS floor-penalty only, (c) no athleticism term, and compare
out-of-sample.

**H7.7 — Our TE rookie policy should be binary.** Take a first-round NFL tight end aggressively at
almost any rookie-draft cost; take no other tight end. The 81.8% / 54.5% first-round split against
≤21% everywhere else is the sharpest discontinuity in this entire corpus. In full PPR with volume
bonuses, a hit tight end is a positional-scarcity weapon in a 10-teamer. Caveat honestly: N=11 on
that first-round cell.

**H7.8 — Encode breakout age and dominator as BOTH a threshold flag and a continuous magnitude.**
Directly from DSnasty_ff's finding that team receiving-yard share adds value on top of breakout age
because breakout age is a threshold that discards how far past 20% a player got. Cheap to implement,
and it is a clean, falsifiable prediction: the continuous term should carry non-zero weight in a
fit that already contains the flag.

**H7.9 — Use the 2nd-best college season, not the best, for RB production inputs.** Heath's
one-hit-wonder correction. Testable against our own rookie RB outcomes as a straight swap.

---

## What could not be sourced

- **No allowlisted RB round-by-round hit-rate table.** The Footballguys RB entry in the "Draft
  Capital Matters" series was scheduled for 2026-07-24 and had not published as of the research
  date. Tried: footballguys.com direct URL pattern, targeted searches restricted to 4for4.com,
  fantasypoints.com, rotoviz.com, playerprofiler.com, dynastyleaguefootball.com,
  sharpfootballanalysis.com. Re-check after 7/24.
- **No peer-reviewed or preprint source.** Searches restricted to arxiv.org, github.io and
  opensourcefootball.com returned nothing on rookie-prospect fantasy modelling. Teramoto et al.
  (2016) on combine measures and NFL RB/WR performance and Meil (2018) both surfaced in general
  search but are hosted on pubmed.ncbi.nlm.nih.gov and scholarworks.calstate.edu, neither of which
  is allowlisted — so they are named here as leads, not cited as evidence.
- **Reddit is unreachable.** Both firecrawl_scrape and WebFetch refused www.reddit.com. Several
  r/DynastyFF threads with apparently quantitative RB hit-rate work
  (e.g. /comments/1t2kehk/predicting_rb_success_2026_prospects_year_2/) could not be read.
- **PFF articles were not retrieved.** Two relevant PFF pieces were found in search
  ("Predicting breakout rookie wide receivers using PFF grades and dominator rating",
  "Fantasy Football: Rookie wide receiver prospect model") but were not scraped within this pass;
  PFF content is typically paywalled. Not claimed as sources.
- **No effect sizes anywhere.** Not one source in this corpus published an R², a coefficient, a
  correlation, or a feature-importance number. Every "adds predictive value" / "strongest predictor"
  claim above is the author's qualitative summary of an unpublished test. This is the single biggest
  weakness of the corpus and the reason Phase 2 must re-derive weights on our own data rather than
  importing anyone's.
