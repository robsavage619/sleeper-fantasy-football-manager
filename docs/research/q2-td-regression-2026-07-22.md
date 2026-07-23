# Q2 — Expected-touchdown models, out-of-sample accuracy, and TD mean reversion

Research date: 2026-07-22. Every number is quoted from a named, linked source. Discrepancies between sources
are flagged rather than averaged away.

## Headline answers, stated up front

1. **Red-zone-bucketed metrics are the wrong construction, and two independent sources say so.** PFF's Scott
   Barrett: "Though frequently cited, red-zone metrics aren't very good at predicting touchdowns." RotoViz
   measured it: for wide receivers, red-zone receiving TDs predict next-season total receiving TDs *worse*
   than raw total receiving TDs do (r-squared 0.029 versus 0.079), and 10-zone TDs worse still (0.018). The
   correct construction is yard-line-weighted, not zone-bucketed.

2. **Expected touchdowns are barely better than raw touchdowns at predicting next-season touchdowns.** This
   is the central null. Barrett's own testing: xTD r-squared 0.283 versus raw TD r-squared 0.275 for
   predicting the following season. A gain of under one percentage point of explained variance. xTD's real
   advantage is that it is much stickier as a *description of role* (0.382 versus 0.276), which is why the
   xTD-minus-TD *differential* carries signal even though the xTD *level* barely outperforms.

3. **Across-season mean reversion is large, reliable, and asymmetric.** 81% of 10+ TD seasons are followed by
   fewer TDs (average -4.8); 95.3% of 14+ TD seasons are (average -8.0). Negative regression is far more
   dependable than positive regression.

4. **Within-season mean reversion of touchdown rate is not established by any allowlisted source.** The one
   source that made falsifiable in-season TD-regression predictions and publicly scored them was losing on
   them at the point sampled, while its efficiency-based predictions were winning. See the Footballguys
   section.

## How expected-TD models are built, and why red zone is the wrong unit

The lineage: Mike Clay created oTD in 2013 as an explicit improvement on red-zone metrics (Barrett credits
this and links https://www.pff.com/news/introduction-to-otd — I did not read that source directly, so treat
the attribution as Barrett's, not verified independently). Barrett then built xTD/XTD on the same idea.

Barrett's stated methodology, quoted from two versions of the same piece:

> "I'm looking at each carry by distance from the end zone (and weighting each carry according to the average
> scoring rate on all identical carries since 2007) and looking at each target by distance from the end zone
> *and* depth of target (and weighting each specific target type based on the average scoring rate on all
> identical targets since 2007). The sum of these numbers gives us a player's total expected touchdowns."

Source: Scott Barrett, "Metrics that Matter: Touchdown efficiency around the league", PFF, 2018-05-23,
https://www.pff.com/news/fantasy-football-metrics-that-matter-touchdown-efficiency

The stated reason red-zone aggregation fails, with numbers:

- Carry from the 1-yard line: 53.9% chance of scoring (PFF version) / 53.8% (Fantasy Points version).
- Carry from the 17-yard line: 3.7% (PFF) / 3.6% (Fantasy Points).

Barrett: "rather than grouping carries from the 1-yard line ... in with carries from the 17-yard line ... and
treating them the same, we'd be better off weighting each carry at each yard line by their actual degree of
scoring probability."

Second source, same author, later version with slightly updated figures: Scott Barrett, "XTD: Top Touchdown
Regression Candidates", Fantasy Points, 2020-08-07,
https://www.fantasypoints.com/nfl/articles/season/2020/xtd-top-touchdown-regression-candidates

Note the important design detail for receiving: the target weighting is two-dimensional — distance from the
end zone *and* depth of target. A 5-yard target from the 8-yard line is a different object from a 5-yard
target from the 40. Any implementation that only uses field position will under-model receivers.

## Out-of-sample accuracy of expected touchdowns

### Barrett's own numbers, both versions

PFF 2018 version, reported as correlations:

> "I found expected touchdowns were just as strong at predicting touchdowns in the following season as raw
> touchdowns (0.52 correlation to 0.52 correlation), but expected touchdowns were much stickier year-over-year
> than raw touchdowns (0.60 correlation to 0.52 correlation)."

Fantasy Points 2020 version, reported as r-squared:

> "I found this stat – expected touchdowns (XTD) – to be even stronger at predicting touchdowns in the
> following season as raw touchdowns (0.283 to 0.275 r^2) and far stickier year-over-year (0.382 to 0.276
> r^2)."

These reconcile almost exactly under the reading that the 2018 numbers are r and the 2020 numbers are
r-squared: 0.52² = 0.270 against a reported 0.275, and 0.60² = 0.360 against a reported 0.382. The small
differences are consistent with two additional seasons of data. This internal consistency is worth noting
because it means we have one study, reported twice, not two independent replications.

**The finding to act on:** expected touchdowns beat raw touchdowns at predicting next-season touchdowns by
0.008 of r-squared. That is a null for the *level*. The 0.106 gap in year-over-year self-stickiness (0.382
versus 0.276) is the real result, and it is what makes the *differential* (actual minus expected) usable as a
regression signal: the expectation persists, the overage does not.

### RotoViz, wide receivers only — a much bleaker picture

Michael Dubner, "Projecting Upside: The Predictability of Receiving Touchdowns", RotoViz, 2018-05-21,
https://www.rotoviz.com/2018/05/projecting-upside-the-predictability-of-receiving-touchdowns/

Sample: WRs from 2008 to 2017 with at least 50 targets in both year N and year N+1; n = 530.

| Year N variable | Year N+1 variable | r-squared |
|---|---|---|
| Total receiving TDs | Total receiving TDs | 0.079 |
| Red-zone receiving TDs | Total receiving TDs | 0.029 |
| 10-zone receiving TDs | Total receiving TDs | 0.018 |

Dubner adds in a footnote that tightening the inclusion criteria to 100 targets and 10 red-zone targets made
"all correlations were even weaker." The remainder of the article, including the in-season correlation table
and the actual predictive model, is behind a RotoViz membership paywall and could not be read.

**Unresolved discrepancy, flagged rather than resolved:** Barrett reports raw TD → next-season TD at r-squared
0.275; Dubner reports 0.079 for the same relationship. The most likely explanation is that Barrett pools all
flex-eligible positions (RB, WR, TE), so a large share of his explained variance is between-position variance
— running backs score more touchdowns than receivers, every year — while Dubner is within-position. If that is
right, Barrett's 0.275 substantially overstates the within-position predictive power that our engine actually
needs. **Unsourced prior — verify empirically in Phase 2**: within a single position, prior-year touchdowns
explain under 10% of next-year touchdowns.

## Across-season mean reversion — effect sizes

### Base rates (unconditional, no model)

Mike Clay, ESPN, using 2012-2024 data:

- 263 instances of a player totalling at least 10 rushing or receiving TDs in a season. **213 of 263 (81.0%)
  scored fewer the next season. Average change: -4.8 touchdowns.**
- 64 instances of 14+ touchdowns. **61 of 64 (95.3%) scored fewer the next year. Average dip: -8.0.** The only
  three exceptions across thirteen seasons: Todd Gurley (19 in 2017 → 21 in 2018), Marshawn Lynch (14 in 2013
  → 17 in 2014), Kyren Williams (15 in 2023 → 16 in 2024).
- Every player who scored 14+ TDs in 2024 scored fewer in 2025: Gibbs 20→18, Cook 18→14, Henry 18→16, Chase
  17→8, Kyren Williams 16→13, Jacobs 16→14, Bijan Robinson 15→11, Barkley 15→9, Hurts 14→8.

Source: Mike Clay, "Fantasy football: Twelve players who will score fewer TDs in 2026", ESPN, 2026-06-26,
https://www.espn.com/fantasy/football/story/_/id/49179383/2026-fantasy-football-rankings-projections-less-touchdowns-td

Barrett's two versions of the same base rate, on flex-eligible players over "the past decade":

- PFF 2018: 129 instances of 10+ TDs (and at least one game played the following year). **Only 8.5% saw an
  increase. Average loss: 5.5 touchdowns.**
- Fantasy Points 2020: 135 instances of 10+ TDs. **Only 11% saw an increase. Average loss: 5.3 touchdowns.**

These three independent-ish framings — 81% decline, 91.5% decline, 89% decline — are not identical because
the samples differ (Clay counts any decline; Barrett's "increase" figures exclude ties). They agree on the
direction and roughly on the magnitude: about five touchdowns lost, on average, from a 10+ TD season.

### Extremes — where the effect is largest

Barrett, Fantasy Points 2020, on the tails of the touchdown-differential distribution over the prior decade:

- **Top 25 seasons by positive TD differential (scored far more than expected): only one player scored more
  touchdowns the following season, and on average the touchdown total declined by 53%.**
- **Bottom 25 seasons (worst differential): 19 of 25 improved the following season, and on average by 66%.**

Note the asymmetry in *reliability*: 24 of 25 (96%) at the positive extreme reverted, versus 19 of 25 (76%)
at the negative extreme. Fading a lucky scorer is a much surer bet than buying an unlucky one. The 66% average
gain at the bottom is off a much smaller base, so the absolute point swing is smaller than the headline
percentage suggests.

Individual extremes cited for scale: Derrick Henry 2019 at +8.7 TDs over expectation (second-largest
differential in twelve seasons); DeAngelo Williams 2008 at +11.8; Jordy Nelson 2011 at +8.2 — Williams and
Nelson "scored a combined 21 fewer touchdowns the following year." At the negative end, Leonard Fournette 2019
at -6.6 (third-worst all time), Matt Forte 2009 at -7.9, Julio Jones 2017 at -7.0; Forte and Jones "each scored
five more touchdowns in their following season."

### Out-of-sample track record of a real, published, dated forecast

This is the closest thing in the corpus to a genuine out-of-sample test, because the predictions were
published before the seasons they covered.

Clay has run the same annual "will score fewer TDs" article every year from 2016 through 2025. **Across those
ten editions there are 151 named players, and in 137 cases the player scored fewer touchdowns the following
season — a 90.7% hit rate.**

The 2025 edition in detail: 21 players named, of whom 20 declined (Zach Charbonnet, 9→12, the lone miss).
**The 21 players averaged 11.7 TDs in 2024, were projected for 8.2 TDs in 2025, and actually averaged 7.6.**

Source: Clay, ESPN, link above.

Three honest caveats on that 90.7%:

- It is a *curated* list, not a random sample. The unconditional base rate for a 10+ TD player declining is
  already 81.0% (Clay's own number). The marginal value added by expectation-based selection over a naive
  "fade every double-digit scorer" rule is therefore roughly ten percentage points of hit rate, not ninety.
- "Scored fewer" is a directional test, not a magnitude test. Getting the sign right 90% of the time says
  nothing about calibration.
- On magnitude the 2025 cohort shows the projections were slightly *optimistic*: projected 8.2, delivered 7.6.
  The direction is right and the size of the fall was under-forecast by about 0.6 TDs per player. One cohort
  is not a calibration study, but it is the only calibration datapoint in this corpus and it points one way.

### Worked examples of the xTD signal in the current cycle

Clay's 2026 list, useful as concrete illustration of what an actual-versus-expected gap looks like in
published form (2025 TDs, 2025 xTD where given, 2026 projected TDs):

- Jonathan Taylor: 20 TDs, 14.4 xTD (3rd in the league), projected 13.
- Dallas Goedert: 11 TDs, 5.1 xTD, projected 6. Within 10 yards of the end zone he was targeted 15 times and
  scored on 11, against a 4.7 xTD on those plays.
- De'Von Achane: 12 TDs, 7.2 xTD, projected 8. His 2024 was aligned (12 TDs, 12.7 xTD); 2025 was not.
- Tucker Kraft: 6 TDs, 1.8 xTD (40th among TEs), projected 4. Also beat expectation in 2024 (7 TDs, 2.8 xTD).
- RJ Harvey: 12 TDs, 8.1 xTD, projected 6.
- Jauan Jennings: 9 TDs, 6.6 xTD, projected 3.
- Travis Etienne: 13 TDs, and a split worth noting — he *underachieved* as a rusher (7 TDs on 8.3 xTD) while
  massively overachieving as a receiver (6 TDs on 2.3 xTD, zero end-zone targets). Projected 8.

The Etienne case is the methodological point in miniature: the rushing and receiving components of xTD can
diverge sharply within one player, and aggregating them hides the signal.

## Within-season mean reversion — the honest state of the evidence

**No allowlisted source published a quantified study of whether touchdown over/under-performance mean-reverts
within a season.** What does exist is one accountability-tracked in-season column, and its results on TD-rate
predictions were poor at the point sampled.

Adam Harstad's "Regression Alert" at Footballguys makes falsifiable four-week predictions and publishes a
running scorecard. The method: split outliers in a statistic into Group A (high) and Group B (low), then
predict Group B outperforms Group A over the next four weeks.

The scorecard as of Week 9 of the 2017 season:

| Statistic | Before prediction | Since prediction | Result |
|---|---|---|---|
| Yards per carry | Group A had 60% more rushing yards/gm | Group B has 16% more | Win |
| Yards per target | Group A had 16% more receiving yards/gm | Group B has 11% more | Win |
| Passing yards per touchdown | Group A had 13% more FP/gm | Group A has 16% more | Losing |
| Receiving yards per touchdown | Group A had 28% more FP/gm | Group A has 61% more | Losing badly |
| Yards per carry (second call) | Group A had 25% more FP/gm | Group A has 11% more | Narrowing |

Source: Adam Harstad, "Regression Alert: Once More Unto The Breach", Footballguys, 2017-11-04,
https://www.footballguys.com/article/HarstadRegression08?article=HarstadRegression08

The pattern is clean and worth stating plainly: **within-season, efficiency metrics (yards per carry, yards
per target) reverted as predicted; touchdown-rate metrics did not.** Harstad's own explanation: "regression
operates over longer timescales. Sometimes outliers can remain outliers for a couple weeks or even a month or
two before reality catches up." He also quantifies how fragile these small samples are — removing Deshaun
Watson alone dropped Group A's lead in the QB prediction from a larger figure to 11%, and in the receiver
prediction from 60% to 26%.

For scale on how extreme an in-season TD-rate outlier can get before reverting: Watson was at an 8.3% TD rate
per pass attempt when flagged in Week 5, and then *increased* to 11.9% over the following two games, reaching
9.3% for the season. Harstad notes only three players since the 1970 merger had a 9%+ TD rate on 200+ attempts
(Stabler 1976, Manning 2004, Watson 2017) — so the underlying claim of unsustainability was correct, and the
four-week window was still lost.

This is a single week's scorecard from a single season. It should not be treated as a study. But it is the
only allowlisted evidence found that directly bears on the within-season question, and it points against
short-horizon TD reversion being tradeable.

## Context: how much of scoring is touchdowns

PFF, in PPR since 2006 — touchdowns as a share of total fantasy scoring: **running backs 21.2%, tight ends
19.6%, wide receivers 17.0%.** In standard scoring: RB 26.7%, TE 31.7%, WR 26.3%.

Source: Barrett, PFF, link above.

This is the sizing constant for how much a TD-regression call can move a projection. In full PPR, correctly
fading a receiver's touchdown luck moves at most about a sixth of his scoring, and typically much less.

## What could not be sourced

- **Any quantified within-season TD mean-reversion study.** Searched: "touchdown regression within season",
  "first half second half TD rate", "rest of season expected touchdowns", restricted to reddit / footballguys
  / rotoviz / establishtherun / substack. Reddit is unreachable through both available fetchers (firecrawl
  returns "we do not support this site"; WebFetch is blocked for reddit.com), so a promising r/fantasyfootball
  thread ("Fantasy Mythbusters: Is touchdown regression real?",
  https://www.reddit.com/r/fantasyfootball/comments/onvtzk/fantasy_mythbusters_is_touchdown_regression_real/)
  could not be read. Its search snippet claims "close to 90% of a receiver's yards to carry over but less than
  60% of their touchdowns" — **that figure is unverified and should not be used.**
- **A proper backtest of any xTD model** with held-out-year MAE, RMSE, or calibration curves. Everything
  published is correlation-based.
- **Positional breakdown of xTD accuracy.** Barrett pools flex positions; nobody published RB-only, WR-only
  and TE-only accuracy for the same model. The RotoViz WR-only numbers use raw and zone TDs, not xTD.
- **An open-source expected-TD implementation on nflverse / opensourcefootball / GitHub with validation.**
  Two searches restricted to opensourcefootball.com, github.com and arxiv.org returned zero results.
- **Rushing versus receiving xTD stickiness separately.** The Etienne example shows they behave differently;
  no source quantified it.
- **Whether xTD itself is stickier than target share or carries.** It is stickier than raw TDs (0.382 vs
  0.276 r-squared) but nobody compared it to the usage metrics from Q1, which run far higher.

## Hypotheses for OUR league

Our format: 10-team full-PPR dynasty. Bonuses: 2.5 for a 100-yard game, 5.0 for 200 yards, 2.5 per 40+ yard
TD, 1.0 for a 20-carry game, 2.5 for 300 passing yards and for 25 completions. These are hypotheses for
Phase 2, not results.

1. **Build xTD yard-line-weighted, never red-zone-bucketed.** This is the one place where the literature gives
   an unambiguous engineering instruction with numbers attached: a 1-yard-line carry converts at ~53.8% and a
   17-yard-line carry at ~3.6%, and RotoViz measured that zone-bucketed TDs predict *worse* than raw TDs
   (0.029 vs 0.079 r-squared). If our engine has any feature named "red zone touches" or "red zone targets"
   feeding a scoring projection, it should be replaced with a per-yard-line probability weight. Check
   `forecast.py` and the valuation constants for this.

2. **Weight receiving expectation by both field position and depth of target.** Barrett's method is
   two-dimensional for targets and one-dimensional for carries. A one-dimensional receiving implementation is
   a known-incomplete model, not a simplification.

3. **Use the differential, not the level.** xTD's level adds essentially nothing over raw TDs for prediction
   (0.283 vs 0.275). Its value is entirely in that it is stickier than actual TDs, so `actual_TD - xTD` isolates
   the non-persistent component. Our engine should surface the differential as the regression flag and should
   *not* claim that xTD is a better TD projection than last year's TD count — that claim is not supported.

4. **Our 40+ yard TD bonus makes touchdown regression cut deeper than in generic scoring, and specifically
   punishes the long-TD scorer.** Barrett's A.J. Brown 2019 case is the archetype: nine TDs averaging 39.0
   yards, five of them from 45+ yards out, against a 4.1 xTD. In generic scoring that player loses six points
   per vanished TD; in ours he loses 8.5. **Prediction: a "long-TD share" feature — what fraction of a player's
   TDs came from 40+ yards — will be a stronger negative predictor of next-season points in our format than in
   half-PPR, because our bonus structure amplifies exactly the least-repeatable TD type.** This is directly
   testable on our own data and is the highest-value single test suggested by Q2.

5. **But full PPR damps TD regression overall.** Touchdowns are 17.0% of WR scoring in PPR against 26.3% in
   standard. Our format is full PPR *with additional yardage and volume bonuses*, which pushes the TD share of
   total scoring lower still. So the *relative* damage from a TD regression is smaller for us than the raw
   effect sizes above imply — except at the 40+ yard tail, per hypothesis 4. These two effects run in opposite
   directions and should be modelled separately, not netted.

6. **Fade the overperformer harder than you buy the underperformer.** The asymmetry is 96% reversion at the
   positive extreme versus 76% at the negative. If our trade engine treats "positive regression candidate" and
   "negative regression candidate" symmetrically, that is miscalibrated. The sell signal is roughly 20
   percentage points more reliable than the buy signal.

7. **Do not act on within-season TD differentials over short horizons.** The only allowlisted in-season
   evidence found shows TD-rate regression calls failing over four-week windows while efficiency regression
   calls succeeded. If our briefing surfaces a "due for positive TD regression this week" style
   recommendation, it is currently unsupported by any source in this corpus. **Unsourced prior — verify
   empirically in Phase 2**: within-season TD differential has near-zero predictive power for the following
   four weeks in our data, and the honest output is a null.

8. **Split rushing and receiving expectation per player.** The Travis Etienne 2025 case (rushing 7 TDs on 8.3
   xTD, receiving 6 TDs on 2.3 xTD with zero end-zone targets) shows a player can be simultaneously unlucky
   and lucky. Aggregate xTD reported him as roughly neutral-to-lucky and hid both signals. Our transaction
   grades and trade valuations should carry the components.

9. **Baseline against the naive rule before claiming the model helps.** Clay's curated list hits 90.7%; the
   unconditional "any 10+ TD season declines" rule hits 81.0%. Any TD-regression feature we ship should be
   evaluated against that 81% null, not against zero. Given how our eval harness treats nulls as first-class,
   this baseline belongs in the eval suite.

10. **Expect the within-position signal to be much weaker than the published pooled numbers.** Barrett's
    0.275 pooled r-squared versus RotoViz's 0.079 WR-only is a factor of three and a half. Our engine
    compares players within a position for start/sit and within a roster for trades, so the within-position
    figure is the relevant one. Calibrating TD-regression confidence off the pooled number would substantially
    overstate what we know.
