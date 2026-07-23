# Q1 — Year-over-year stickiness: usage versus efficiency, by position

Research date: 2026-07-22. Every number below is quoted from a named, linked source. Where a source is
ambiguous about whether it published r or r-squared, that ambiguity is flagged rather than resolved by guessing.

## Headline answer

Opportunity is stickier than efficiency at every position, and the gap is large. The cleanest single
statement comes from Sharp Football Analysis: for running backs, the best efficiency/rate statistic in
year-over-year rollover would rank 17th if it were dropped into the list of counting statistics. For wide
receivers, the best rate statistic would rank 8th on the combined list. The gap is therefore wide at RB and
merely large at WR — which is itself the interesting finding, because it means efficiency carries a bit more
signal for pass-catchers than for rushers.

Sources: Rich Hribar, "Running Back Stats That Matter for Fantasy Football", Sharp Football Analysis,
https://www.sharpfootballanalysis.com/fantasy/running-back-stats-that-matter-fantasy-football-2024/ and
Rich Hribar, "Wide Receiver Stats That Matter for Fantasy Football", Sharp Football Analysis,
https://www.sharpfootballanalysis.com/fantasy/wide-receiver-stats-that-matter-fantasy-football-2024/

## A note on r versus r-squared — read this before using any number

Two of the three main sources report different quantities and it matters:

- Sharp Football Analysis (Hribar) labels its columns "YOY R2". Taken at face value these are r-squared values.
- 4for4 (Hoopes) labels its columns "Correlation" and describes them as "the correlation of a variable between
  consecutive seasons" — these are r values.
- SumerSports describes "correlation ... on a scale of 0 to 1" — r values.

These reconcile reasonably well under that reading. Hribar's WR team target share YoY figure is 0.4013; if that
is r-squared, r is about 0.63, which sits close to SumerSports' reported target-share correlation of "around
0.70" and 4for4's targets-per-game correlation of 0.70. That consistency is the main reason to trust the
r-squared reading of the Sharp tables. It is not proof. Treat any cross-source arithmetic as approximate and
verify on our own data in Phase 2.

## Wide receiver

### Sharp Football Analysis — year-over-year, counting stats (labelled R-squared)

| Category | YoY |
|---|---|
| PPR Pts/Gm | 0.5669 |
| 0.5 PPR Pts/Gm | 0.5537 |
| Targets/Gm | 0.5391 |
| Receptions/Gm | 0.5205 |
| PPR Pts/Season | 0.5158 |
| Receiving Yds/Gm | 0.4944 |
| Receptions/Season | 0.4128 |
| Targets/Season | 0.4039 |
| Receiving Yds/Season | 0.3971 |
| Routes/Gm | 0.3211 |
| Receiving TD/Gm | 0.2064 |
| Receiving TD/Season | 0.1984 |
| Routes/Season | 0.1935 |
| Games Played | 0.0224 |

### Sharp Football Analysis — year-over-year, efficiency/rate stats

| Category | YoY |
|---|---|
| Yards/Team Attempt | 0.4668 |
| Team Target % | 0.4013 |
| Target/Route % | 0.3916 |
| Air Yards/Target | 0.3792 |
| Yards/Route Run | 0.2808 |
| YAC/Reception | 0.1351 |
| Catch % | 0.1129 |
| Yards/Catch | 0.1059 |
| Yards/Target | 0.0278 |
| First Downs/Target | 0.0234 |
| TD/Target % | 0.0082 |

Source: Rich Hribar, Sharp Football Analysis,
https://www.sharpfootballanalysis.com/fantasy/wide-receiver-stats-that-matter-fantasy-football-2024/

Key observations Hribar draws himself: "Opportunity is the name of the game. Statistics related to targets
carry heavy weight year over year"; "Targets matter more than routes run"; "Efficiency (or lack thereof) per
target and reception have the lowest correlation to future output." Note the ordering inside the efficiency
table: the four survivors are all opportunity-flavoured rate stats (yards per team attempt, team target share,
target rate per route, air yards per target). Genuine efficiency — yards per target, YAC per reception, TD per
target — collapses. TD/Target at 0.0082 is effectively zero.

### 4for4 — year-over-year self-correlation, r (2017-2023, WRs with 30+ targets in consecutive seasons)

Slot Rate 0.75; Targets Per Game 0.70; Fantasy Points Per Game 0.68; Receptions Per Game 0.68; Yards Per Game
0.67; Average Depth of Target 0.65; Targets Per Route Run 0.64; Open Score 0.59; First Downs Per Route Run
0.58; Average Depth of Completion 0.57; Yards Per Route Run 0.56; YAC Per Reception 0.48; Points Earned Per
Route 0.43; YAC Score 0.43; Yards Per Reception 0.42; Broken/Missed Tackles Per Reception 0.39; Catch Score
0.27; On-Target Catch Percentage 0.22; TD Rate 0.19; EPA Per Target 0.18; Drop Rate 0.14; Contested Catch Rate
0.02; Route Rate 0.01.

### 4for4 — correlation with NEXT season's fantasy points per game, r

Fantasy Points Per Game 0.68; Yards Per Game 0.67; Targets Per Game 0.62; Receptions Per Game 0.61; Yards Per
Route Run 0.59; First Downs Per Route Run 0.57; Targets Per Route Run 0.53; Points Earned Per Route 0.47; Open
Score 0.44; Catch Score 0.31; EPA Per Target 0.28; YAC Score 0.17; Yards Per Reception 0.15; TD Rate 0.13;
Contested Catch Rate 0.12; Average Depth of Completion 0.10; Broken/Missed Tackles Per Reception 0.10; Average
Depth of Target 0.07; YAC Per Reception 0.05; On-Target Catch Percentage 0.05; Route Rate -0.05; Drop Rate
-0.09; Slot Rate -0.12.

Source: Stephen Hoopes, "The Most Predictable Wide Receiver Stats", 4for4,
https://www.4for4.com/2024/preseason/most-predictable-wide-receiver-stats

Two things worth extracting. First, sticky does not mean predictive: slot rate is the single stickiest WR
variable (r = 0.75) and is *negatively* correlated with next-year points (-0.12). Stickiness and predictive
value must be tracked as separate columns in any engine feature table. Second, WR is the position where
efficiency partially survives: yards per route run (0.59) and first downs per route run (0.57) are predictive
of next-season points at close to the level of targets per game (0.62). This is the exception to "opportunity
beats efficiency" and it is receiver-specific.

Hoopes on YAC-type metrics specifically: "YAC After Catch Per Reception" self-correlates at 0.48 but predicts
next-season points at 0.05 — a strong sticky/predictive divergence, and directly relevant to the question of
whether YAC over expected is worth modelling.

## Running back

### Sharp Football Analysis — year-over-year, counting stats

Touches/Game 0.5668; RuAtt/Game 0.5619; Yards From Scrimmage/Game 0.5364; RuYd/Game 0.5227; PPR Pts/Game
0.5141; Targets/Game 0.4767; Snaps/Game 0.4582; Receptions/Game 0.4518; Touches/Season 0.4447; 0.5 Pts/Game
0.4238; YFS/Season 0.4178; ReYd/Game 0.4066; PPR Pts/Season 0.3977; 0.5 Pts/Season 0.3936; Snaps/Season
0.3465; Routes/Gm 0.3071; Targets/Season 0.2688; Receptions/Season 0.2661; ReYds/Season 0.2332; RuTD/Game
0.2289; RuAtt/Season 0.2221; RuYd/Season 0.2009; Routes/Season 0.1653; RuTD/Season 0.1207; ReTD/Gm 0.0994;
ReTD/Season 0.0663; Games/Season 0.0015.

### Sharp Football Analysis — year-over-year, efficiency/rate stats

Air Yards/Target 0.2908; Targets/Route Run % 0.2533; Team Target % 0.2533; Rushing Yds After Contact/Rush
0.1894; Yards/Route Run 0.1688; Rushing Yds Before Contact/Rush 0.0845; First Downs/Rush % 0.0625; Stuff %
0.0589; First Downs/Target 0.0558; YAC/Catch 0.0471; Team TD % 0.0441; Explosive Run % 0.0341; Yards/Carry
0.0312; EPA/Rush 0.0231; Yards/Catch 0.0131; TD/Rush % 0.0091; Yards/Touch 0.0083.

Source: Rich Hribar, Sharp Football Analysis,
https://www.sharpfootballanalysis.com/fantasy/running-back-stats-that-matter-fantasy-football-2024/

Hribar's own summary: "Tread lightly with rushing efficiency stats from the previous season, they are almost
completely descriptive and carry next to zero top-down correlation for previous efficiency output." Yards per
carry at 0.0312 and yards per touch at 0.0083 are, for practical purposes, noise.

Note the sign of the gap between positions on the *same* metric: team target share is 0.4013 for WRs and
0.2533 for RBs in Hribar's tables. A running back's share of the passing game is roughly 60% as stable as a
receiver's, before any team change is even considered.

### 4for4 — year-over-year self-correlation, r (2018-2023, RBs with 100+ attempts in consecutive seasons)

Receptions Per Game 0.70; Receiving Yards Per Game 0.68; Routes Per Game 0.64; Rush Attempts Per Game 0.61;
Fantasy Points Per Game 0.57; Time Behind Line of Scrimmage 0.54; Elusive Rating 0.51; Targets Per Route Run
0.50; Yards After Contact Per Attempt 0.44; Avoided Tackles Per Attempt 0.43; 8+ Defenders in Box Rate 0.41;
Yards Per Route Run 0.39; Yards Per Attempt 0.37; Breakaway Rate 0.36; Explosive Runs Per Attempt 0.34; RYOE
Per Attempt 0.33; Points Earned Per Play 0.29; EPA Per Attempt 0.22; First Downs Per Attempt 0.20; Success
Rate 0.16; Receiving TD Rate 0.08; Fumbles Per Attempt 0.08; Rush TD Rate 0.05.

### 4for4 — correlation with NEXT season's fantasy points per game, r

Fantasy Points Per Game 0.57; Receiving Yards Per Game 0.50; Receptions Per Game 0.47; Routes Per Game 0.39;
Yards Per Route Run 0.37; Rush Attempts Per Game 0.35; Targets Per Route Run 0.32; Explosive Runs Per Attempt
0.22; Rush TD Rate 0.21; Yards Per Attempt 0.20; Yards After Contact Per Attempt 0.18; RYOE Per Attempt 0.18;
Elusive Rating 0.18; Time Behind Line of Scrimmage 0.16; Breakaway Rate 0.15; Fumbles Per Attempt 0.15; EPA
Per Attempt 0.15; Avoided Tackles Per Attempt 0.14; Points Earned Per Play 0.13; First Downs Per Attempt 0.11;
Receiving TD Rate 0.10; Success Rate 0.01; 8+ Defenders in Box Rate -0.07.

Source: Stephen Hoopes, "The Most Predictable Running Back Stats", 4for4,
https://www.4for4.com/2024/preseason/most-predictable-running-back-stats

The headline here is that a running back's *receiving* usage is the stickiest and most predictive thing about
him — receptions per game (0.70 sticky, 0.47 predictive) and receiving yards per game (0.68 sticky, 0.50
predictive) beat rush attempts per game (0.61 / 0.35). Hoopes: "We're six variables deep before we hit a
running-based statistic for running backs."

Rush TD rate self-correlates at 0.05 — the lowest number in the RB table. This is directly relevant to Q2.

### SumerSports corroboration

SumerSports' own year-over-year study (players with 100+ key snaps in two consecutive seasons, since 2021)
reports: target share correlation "around 0.70"; yards per route run "greater than 0.60"; QB EPA per pass
attempt "about 0.60"; QB sack-avoidance metrics "in or around 0.50"; and for rushers, the *stickiest* stat is
tackled-for-loss percentage "at around 0.40", with EPA per rushing attempt showing "a virtually negligible
correlation". Their bottom line: "Be heavily skeptical of rushing stats when trying to predict how good a
running back will be in the upcoming season."

Source: Sam Bruchhaus, "Sticky Football Stats: Predictive NFL Metrics", SumerSports,
https://sumersports.com/the-zone/sticky-football-stats-predictive-nfl-metrics/

They also flag a selection-effect caveat that applies to every number on this page: the sample is restricted
to players who were on the field in two consecutive seasons. "Availability is the best ability ... even
achieving volume in two straight seasons is an accomplishment." Every stickiness figure here is conditional
on survival.

## Tight end

Sharp Football Analysis, year-over-year (labelled R-squared):

ReYd/Game 0.6089; Rec/Game 0.5995; Tgt/Game 0.5967; Yards/Team Attempt 0.5625; PPR Pts/Game 0.5582; ReYd/Season
0.5581; 0.5 Pts/Game 0.5448; Team Target % 0.5404; Rec/Season 0.5346; Targets/Season 0.5319; PPR Pts/Season
0.4949; Routes Run 0.4879; 0.5 Pts/Season 0.4659; ReTD/Game 0.2445; ReTD/Season 0.2165; Yards/Route 0.1891;
Target/Route % 0.1648; Catch % 0.0978; Air Yards/Target 0.0787; Games Played 0.0711; Route/Snap % 0.0529;
Yards/Catch 0.0525; Yards/Target 0.0465; TD % 0.0002.

Source: Rich Hribar, "Tight End Stats That Matter for Fantasy Football", Sharp Football Analysis,
https://www.sharpfootballanalysis.com/fantasy/te-stats-that-matter-fantasy-football/

Hribar: "From a top-down perspective, the tight end position is the most stable position in terms of yearly
production being a signal for the following year." Ten of 24 TE metrics clear 0.50, versus five of 30 for RB
and five of 24 for WR. Team target share is *more* stable for TEs (0.5404) than for WRs (0.4013). Target rate
per route, by contrast, is roughly half as stable for TEs (0.1648) as for WRs (0.3916) — TE opportunity is
governed by how often they are on the field running routes at all, not by per-route target earning.

TE TD% year-over-year is 0.0002. That is the single most emphatic null in this entire corpus.

## WOPR and air yards specifically

PFF published concrete WOPR stability numbers. Joseph Bryan reports that WOPR (defined as 1.5 × target share
+ 0.7 × air yards share) has "a .47 R-squared (Rsq) when predicting N+1 WOPR for the 2023 season without any
route threshold", and that his Predicted WOPR variant reaches .66 R-squared on the same task — "a .19 raw Rsq
stability enhancement over the most recognized receiving metric available." Separately, three-week actual
WOPR explains 79% of the variance in three-week fantasy points per game — but Bryan is explicit that this is
descriptive, not predictive: "we are not yet predicting future outcomes."

Source: Joseph Bryan, "Route-based heroes: Identifying players who could break out in fantasy and DFS in Week
7", PFF, 2024-10-17,
https://www.pff.com/news/fantasy-football-route-based-heroes-identifying-players-who-could-break-out-in-fantasy-and-dfs-in-week-7

Caution on the .47: that is week-over-week (N+1 within a season), not season-over-season. Do not mix it with
the annual figures above.

On air yards generally, FTN Fantasy states that among 2020 WRs, air yards correlated with actual receiving
yards at "a linear r-squared over 0.85" — but that is a within-season descriptive relationship, not
stickiness, and FTN is not on the allowlist so this is reported as a search-result snippet only and should be
treated as unverified. FTN URL for the record: https://ftnfantasy.com/nfl/air-yards

## What could not be sourced

- **YAC over expected (YACOE) year-over-year stickiness, as a named metric.** No allowlisted source published
  an r or r-squared for YACOE specifically. The closest available proxies are 4for4's "YAC Per Reception"
  (WR self-correlation 0.48, next-season predictive 0.05) and "YAC Score" (0.43 / 0.17), and Hribar's
  "YAC/Reception" (WR 0.1351, RB YAC/Catch 0.0471). Next Gen Stats publishes YACOE as a leaderboard but no
  stickiness study was found on nextgenstats.nfl.com. Searches tried: YACOE stickiness, yards after catch over
  expected year over year, Next Gen Stats YAC over expected predictive.
- **Snap share year-over-year, as its own metric.** Hribar reports Snaps/Game for RBs (0.4582) and
  Routes/Gm for WRs (0.3211), but no source gave a clean positional snap-*share* stickiness number.
- **Carries (raw) versus carry share.** Sources report rush attempts per game, not share of team carries. The
  distinction matters for us because backfield committee structure is exactly what a share normalises away.
- **Any opensourcefootball.com post on metric stability.** Searched; the site's posts that surfaced were about
  team win stability, not player usage stickiness. No allowlisted opensourcefootball article on this question
  was found.
- **Dynasty-specific (multi-year horizon) stickiness.** Everything above is one-year-ahead. Nothing citable
  was found for two- and three-year-ahead decay of usage metrics.

## Hypotheses for OUR league

Our league is 10-team full-PPR dynasty with bonuses: 2.5 for a 100-yard game, 5.0 for 200 yards, 2.5 per 40+
yard TD, 1.0 for a 20-carry game, 2.5 for 300 passing yards, 2.5 for 25 completions. Volume outliers and big
plays are worth strictly more here than in generic scoring. The following are hypotheses to test in Phase 2,
not established results.

1. **Our scoring should push the engine even harder toward opportunity than the generic literature implies.**
   The 20-carry bonus (1.0) and the 100/200-yard bonuses are threshold functions of volume. A threshold bonus
   converts a sticky, well-estimated quantity (expected touches) into points without routing through the
   unstable efficiency layer. Weighting projected touches/targets above projected efficiency should therefore
   be *more* correct in our format than in half-PPR.

2. **But the 40+ yard TD bonus and the 200-yard bonus cut the other way, and they specifically reward the
   least sticky things we measure.** Big-play production is governed by explosive run rate (RB YoY r = 0.34,
   next-season predictive 0.22 per 4for4), breakaway rate (0.36 / 0.15), and TD rate (rush TD rate 0.05 /
   0.21). Our format pays a premium for exactly the traits that do not carry. Prediction: the marginal points
   from big-play bonuses will be substantially *less* forecastable than baseline points, so bonus-inclusive
   projections should carry wider intervals than bonus-exclusive ones. If our forecast module reports
   symmetric error bars on bonus-heavy players it is understating variance.

3. **Threshold bonuses should be modelled as probabilities, not as expected-value add-ons.** A 1.0 bonus for
   20 carries is worth 1.0 × P(carries ≥ 20), and that probability is a step function of a back's role, not a
   linear function of his mean. Two backs projected for 16 carries can have very different P(≥20) depending on
   whether the backfield is a committee or a bell-cow with occasional 25-carry scripts. Unsourced prior —
   verify empirically in Phase 2 — that using mean carries × bonus systematically underrates bell-cows and
   overrates committee backs in our format.

4. **The receiving-back is even more valuable here than the literature says, and for a second reason.**
   4for4 shows RB receptions per game is the stickiest RB metric (0.70) and second-most predictive (0.47).
   In full PPR that usage is directly monetised. But note the 20-carry bonus does *not* reward receptions, so
   the ideal RB archetype for us is the back who both carries 20 and catches — a narrow population. Prediction:
   in our format the value gap between true three-down backs and pass-catching committee backs is wider than
   generic dynasty ADP implies.

5. **Corroboration of our own finding on RB usage portability.** Hribar's tables give RB team target share a
   year-over-year figure of 0.2533 versus WR 0.4013 — RB usage is roughly 60% as stable as WR usage even
   *without* conditioning on a team change. SumerSports independently concludes "environment matters. A lot"
   for rushers and names Barkley, Henry and Jacobs as the illustration. This is directionally consistent with
   our observed ~17% (team change) versus ~48% (stayed) explanatory power for RBs, and with receivers'
   usage carrying. The published literature does not contradict our data; it did not split by team change, so
   it cannot confirm the specific 17/48 split either.

6. **Our engine should carry a "sticky" flag and a "predictive" flag as separate fields.** The slot-rate case
   (0.75 sticky, -0.12 predictive) is the proof that they dissociate. Any feature-importance display in the
   briefing that conflates them will mislead. This is cheap to implement and directly testable.

7. **TD-rate features should be near-zero-weighted at every position and hard-zero at TE.** TE TD% YoY is
   0.0002; WR TD/Target% is 0.0082; RB TD/Rush% is 0.0091. If any of our valuation constants give prior-season
   TD rate meaningful weight, that is a calibration bug, not a modelling choice.

8. **Selection effects will bite us harder than they bite the published studies.** Every stickiness number
   above conditions on the player being active in both seasons. In a 10-team dynasty with deep rosters we hold
   players *through* the seasons where they are not active, so our realised stickiness on a full roster will
   be lower than the published figures. Unsourced prior — verify empirically in Phase 2 — that the
   availability-adjusted stickiness of target share on our roster is meaningfully below 0.70 r.
