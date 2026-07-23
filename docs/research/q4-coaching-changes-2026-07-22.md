# Q4 — Coaching, OC and play-caller changes

Research date: 2026-07-22. Question: what are the measured effects of a coaching / OC / play-caller
change on team pass rate, play volume and pace, and on incumbent player usage in year one? How much
does scheme continuity matter?

This file is written directly against a finding already established on our own league data:

> A new play-caller costs a running back nearly as much usage carryover as a new team
> (correlation gap -0.216 staying put vs -0.279 moving).

The sections below corroborate or contradict that, and I say which.

Honest framing up front: the published literature on this question is thin and mostly qualitative.
Nobody in the allowlisted corpus has published a clean before/after study of "incumbent player usage
in year one under a new play-caller" with effect sizes. What exists is (a) rigorous work on how much
of pass rate is attributable to team/coach versus game situation, (b) year-over-year stability
coefficients for player-level stats that bound how much *anything* carries over, and (c) a large
body of analyst commentary tracking individual play-callers' tendencies across employers. I have
used (a) and (b) as the quantitative spine and treated (c) as pattern evidence, labelled as such.

---

## 1. Scale of the 2026 disruption — this is not a normal year

The base rate matters for how much weight this factor should carry right now.

- 21 of 32 NFL teams changed offensive coordinators this offseason. Jack Miller at Establish The Run:
  "It's worth mentioning that 21 NFL teams this year have a new offensive coordinator — far more
  turnover than usual." (Jack Miller, Establish The Run, "Team Play-Calling Trends From the 2025
  Season", 2026-04-19, https://establishtherun.com/team-play-calling-trends-from-the-season/)
- ESPN puts the play-caller count even more starkly: "More than half of the league will have a new
  offensive playcaller this season." (ESPN, "Questions about 10 new NFL coordinators entering 2026
  season", https://www.espn.com/nfl/story/_/id/49166861/new-nfl-coordinators-offense-defense-questions-2026-season-cowboys-bills-commanders)

Note that OC changes and *play-caller* changes are not the same event and the distinction is
load-bearing for our engine. Several teams have a nominal new OC while the head coach retains
play-calling (continuity), and several have the same OC while play-calling duties move (discontinuity
without a personnel change). Examples from the 2025 cycle documented by PlayerProfiler: Kevin
Stefanski announced he would resume play-calling in Cleveland despite promoting Tommy Rees to OC;
Liam Coen confirmed he would call plays in Jacksonville over new OC Grant Udinski; Kellen Moore
confirmed he would call plays in New Orleans over new OC Doug Nussmeier; and San Francisco's new OC
"replaces absolutely no one, as Kyle Shanahan is so in control of the 49ers' offense that they
didn't even bother to have an offensive coordinator in 2024." (Ted Chmyz, PlayerProfiler,
"Fantasy Football Implications of 2025 NFL Coaching Changes",
https://www.playerprofiler.com/article/fantasy-football-implications-of-2025-nfl-coaching-changes-can-ben-johnson-save-caleb-williams/)

**Implication for our engine**: if we are keying off an `oc_change` boolean scraped from a roster of
coordinators, we are measuring the wrong event. The correct feature is *who calls the plays*, which
is often the head coach and is frequently unchanged when the OC title changes.

---

## 2. How much of pass rate is actually the coach?

This is the best-quantified piece of the question and it comes from Open Source Football.

Richard Anderson built an xgboost model predicting QB dropback probability from game state (down,
distance, yard line, score differential, quarter, half seconds remaining, timeouts) on 2016–2019
play-by-play, then fed its output into a Bayesian multilevel model with team-season random effects
to isolate the team/coach tendency net of game script.

Model performance: 69.1% accuracy, 0.760 AUC on held-out data — his own read is that this is
appropriate, "If we could perfectly predict dropback probability from game state it would be very
easy to be an NFL defensive coordinator!"

The parameter that answers our question is `sigma_mu = 0.18` (log-odds scale, 95% interval
0.16–0.21). His interpretation, quoted directly:

> "The .18 value of `sigma_mu` means that our predicted probabilities for different teams would
> range from about .52 on the low end and .69 on the high end for a play where an average team is
> at .6."

(Richard Anderson, Open Source Football, "Estimating Run/Pass Tendencies with tidyModels and
nflfastR", 2020-09-08,
https://www.opensourcefootball.com/posts/2020-09-07-estimating-runpass-tendencies-with-tidymodels-and-nflfastr/)

**Read this carefully, because it cuts both ways.** A team/coach identity moves situational pass
probability by roughly ±8 percentage points at the extremes of a 32-team distribution. That is
large in fantasy terms — 8 points of pass rate across ~1,050 plays is on the order of 80 plays
reallocated between the passing and running games over a season. But it is also bounded: the *game
state* is doing most of the work. A single team-season effect is one standard deviation of 0.18 in
log-odds; the typical coaching change moves a team some fraction of that distance, not the full
0.52-to-0.69 span.

Anderson's substantive finding also matters for how we interpret raw pass rate: "teams that run the
ball the most are not necessarily the run-heaviest teams." He highlights that the Patriots
"consistently run more than average but are among the pass-heavier teams once game script is
accounted for," and that the Rams and Saints also look more aggressive than raw dropback% suggests.

**Corroborating evidence that game situation dominates coach identity.** An independent replication
by Amrit Vignesh tried to improve the xPass model by adding the possessing team's passing and
rushing quality (scaled EPA/play from prior weeks). His result: "both variables only showed to have
3% importance in the model each," against situational variables (yard line, home/away, half seconds
remaining, down, distance, score differential, timeouts, pre-snap win probability). He is candid
that this "did diminish the purpose of my model." (Amrit Vignesh, Medium, "NFL Pass Rate Over
Expected By Coach Adjusted by Team Quality", 2024-07-13,
https://medium.com/@amritvignesh/nfl-pass-rate-over-expected-by-coach-adjusted-by-team-quality-cb4d69518c8b)

That is a genuine null and should be recorded as one: adjusting expected pass rate for how good the
offense actually is at passing versus running barely changes the model. Situation is the dominant
term; team/coach is a modest residual; team *quality* is a rounding error.

---

## 3. Play-caller changes mid-season: a natural experiment

The cleanest observable effect in the corpus is the 2025 Detroit Lions, because the play-caller
changed mid-season with personnel held fixed.

Establish The Run's account: "The Lions began 2025 with eight straight games with a negative Pass
Rate Over Expectation, peaking with a -3% PROE during that stretch. The Lions' first game with a
positive PROE came in Week 10, which also marked Dan Campbell's first game calling plays after
taking those duties over from the now-fired John Morton. The Lions had four games with a positive
PROE over the second half of the year with Campbell calling plays."
(Jack Miller, Establish The Run, link above)

Same roster, same quarterback, same season, one variable changed — and the sign of PROE flipped.
This is the single best piece of evidence in the corpus that the play-caller, specifically, moves
team pass rate.

ETR's own forward-looking caution is worth encoding as a modelling rule: they warn that Drew
Petzing's 2025 Arizona offense was "the NFL's pass-heaviest offense" but that "they admittedly fell
into some extreme game scripts and basically gave up on their season down the stretch," and that
"Petzing led two run-first offenses with the Cardinals in 2023-24, so it seems difficult to consider
him a major boon for team pass rate despite what happened with the Cardinals last season."

**Rule extracted**: a play-caller's most recent season pass rate is contaminated by that team's
game scripts. Use his multi-year record, situation-adjusted, not his last year raw.

ETR is also explicit that a play-caller change breaks the usefulness of the historical data
entirely: "That makes this more difficult than usual because the data becomes much less useful with
a change in play-caller." That is a professional forecaster stating that his team-level priors do
not survive the change. Directly consistent with our own -0.216 finding.

---

## 4. Play-caller tendency travels with the person — the strongest usage evidence

The most citable evidence that play-caller identity determines *player usage* (not just pass rate)
is Ted Chmyz's Kellen Moore observation:

> "In his six years as an OC, Moore's teams have never ranked higher than 19th in the league in RB
> target share, with an average ranking of 23rd. That's despite having talented receiving backs in
> Ezekiel Elliott, Tony Pollard, Austin Ekeler, and Saquon Barkley."

(Ted Chmyz, PlayerProfiler, link above)

Six seasons, four different franchises, four genuinely capable pass-catching backs, and the RB
target share ranking never once cracked the top 18. That is a persistent, personnel-independent
usage signature attached to the play-caller. It is exactly the mechanism our -0.216 finding is
detecting: when the play-caller changes, the incumbent RB's usage snaps toward the new caller's
signature rather than persisting from his own history.

Chmyz documents the same pattern in the other direction with other callers:
- Klint Kubiak's 2024 Saints "led the league last season with an absurd 26-percent of their targets
  going to running backs" — and Chmyz projects that tendency forward to Seattle's backs.
- Liam Coen's 2024 Buccaneers "rank third in the league in running back targets."
- Ben Johnson's 2022 Lions used D'Andre Swift for "99 carries, 163 fewer than Jamaal Williams and
  only 57 more than Justin Jackson" — the basis for Chmyz calling Swift a loser on Johnson's arrival
  in Chicago despite Swift being an obvious archetype fit.

He also documents pass-rate transfer as a projected downgrade: Seattle "ranked fifth in both raw
pass rate and pass rate over expected" in 2024, while "Kubiak's Saints... had the eighth-lowest pass
rate vs. expected in the league" and "His 2021 Vikings team was also well below average in pass
rate."

Caveat, stated plainly: these are the analyst's selected examples, not a systematic study, and they
are subject to exactly the post-hoc-selection failure mode. They corroborate a mechanism; they do
not establish an effect size. Treat as pattern evidence.

---

## 5. What bounds carryover in the first place: year-over-year stickiness

Even with zero coaching change, most football statistics do not carry over well. This is the
ceiling that any coaching-change effect has to be measured against, and it is the finding that best
explains *why* our RB number is so much worse than our pass-catcher number.

SumerSports (Lindsay Rhodes and Sam Bruchhaus) computed year-over-year correlations since 2021 for
players with 100+ snaps in consecutive seasons (Sam Bruchhaus, SumerSports, "Sticky Football Stats:
Predictive NFL Metrics", 2025-07-14,
https://sumersports.com/the-zone/sticky-football-stats-predictive-nfl-metrics/):

| Statistic | Position group | YoY correlation |
|---|---|---|
| Target share | WR/TE | ~0.70 |
| Yards per route run | WR/TE | >0.60 |
| EPA per pass attempt | QB | ~0.60 |
| Sack avoidance metrics | QB | ~0.50 |
| Tackled-for-loss % (the *stickiest* rushing stat) | RB | ~0.40 |
| EPA per rush attempt | RB | "virtually negligible" |

Their conclusions, quoted:
- "wide receivers and tight ends have the highest correlations between many of their key stats
  year-over-year"; target share "has been the 'stickiest' metric since 2021."
- On backs: "rushing stats, across the board, have some of the lowest year-over-year correlations.
  The major theme here: environment matters. A lot."
- Summary advice: "Trust receiver rate stats, particularly if they are describing the player's
  usage" and "Be heavily skeptical of rushing stats when trying to predict how good a running back
  will be in the upcoming season."

**This directly corroborates our own result.** Our finding is that a play-caller change hurts RB
usage carryover almost as much as a team change. SumerSports explains the mechanism: RB production
is an environment variable wearing a player's name. Pass-catcher usage is a player property
(target share ~0.70); rushing production is a scheme property (EPA/rush ~0). When the scheme
changes, the RB's number changes, because the number was never his.

It also predicts, correctly, why our Q5 finding is the mildest of the three disruptions: target
share is the stickiest stat in football, so it survives environment shocks better than anything
else in the corpus.

SumerSports' own caveat about the whole exercise deserves repeating in our documentation: "the
correlations between year-over-year performance are not as high as in other sports," and they
attribute this to football's weak-link, 22-player, injury-prone structure.

---

## 6. Effect on the quarterback specifically

PFF's study of quarterbacks under changing offensive coordinators is a decade old and entirely
case-study based (Andy Dalton, Matt Ryan, Matthew Stafford, Roethlisberger, Luck), so it carries no
effect size. But its summary judgment is a citable directional claim, and it is a *null-leaning*
one: "In most cases, shifting an offensive coordinator has a relative minor correlation on what fans
see on Sundays. However, in some cases, the results of a new offensive coordinator can be drastic
for a QB, both positively and negatively."
(Aaron Resnick, PFF, "QB Study: The positive, and negatives, of shifting a quarterback's offensive
coordinator", 2017-07-18,
https://www.pff.com/news/pro-qb-study-the-positive-and-negatives-of-shifting-a-quarterbacks-offensive-coordinator)

The case detail worth noting is the second-year pattern: PFF observes that Matt Ryan's "overall
grades have dropped off in his second season under both Mularkey and Koetter" while he "performed
great in his first season under a new offensive coordinator." That is the opposite of the
conventional "year two in the system" prior. One quarterback, five data points — anecdote, not
evidence, but it is a hypothesis worth testing rather than assuming.

SumerSports adds the relevant caution for QB projection under a change: "Leverage EPA for
quarterbacks but always take scheme and team changes into consideration," noting that EPA "is
technically a team statistic" that bundles the offensive line, receivers, and the coordinator's
scheme.

---

## 7. Play volume and pace — no allowlisted quantitative source found

This is a genuine gap.

Establish The Run frames pace and pass rate as the two inputs to team volume — "The two key
variables for projecting team-level volume output are play volume and pass rate" — and names Pat
Thorman as their pace forecaster, but the actual pace forecasting content is behind their Draft Kit
paywall (the article body cut off at a subscription wall).

Searches restricted to 4for4.com, footballoutsiders.com, sumersports.com, opensourcefootball.com,
espn.com, pff.com and substack.com for pace stability and seconds-per-play year-over-year returned
only current-season stat tables (Sharp Football's NFL Pace Stats page, teamrankings, nfelo,
RotoWire), not analysis of how pace responds to a coaching change or how stable it is season to
season.

**No allowlisted source found** for: the year-over-year correlation of situation-neutral pace; the
measured change in plays per game after a coaching change; or whether pace is a coach property or a
roster property. Everything I believe about this is **unsourced prior — verify empirically in
Phase 2**, and it is directly computable from nflverse play-by-play we already load:
situation-neutral seconds-per-play by team-season, regressed on prior season with a play-caller-change
interaction.

---

## 8. Reading the corpus against our own numbers

**Our finding**: new play-caller costs an RB nearly as much usage carryover as a new team
(-0.216 staying put vs -0.279 moving).

**Corroborated.** Three independent strands support it:
1. SumerSports' stickiness table gives the mechanism — rushing production has essentially no
   player-attributable year-over-year signal (EPA/rush ≈ 0, best rushing stat ≈ 0.40), so an RB's
   usage is a scheme output, and changing the scheme should destroy nearly as much of it as changing
   the entire environment.
2. Chmyz's Kellen Moore observation shows a play-caller carrying a rigid RB-usage signature across
   four teams and four different capable receiving backs — i.e. the caller, not the back, sets the
   role.
3. ETR, a professional forecasting shop, states outright that team play-calling data "becomes much
   less useful with a change in play-caller," and the Detroit mid-season play-caller swap flipped
   the sign of PROE with personnel held constant.

**Not contradicted by anything found.** The one source that leans null — PFF's "relative minor
correlation" — is about quarterback *grade*, not running back *usage*, is a decade old, and is
case-study based. It does not bear on our claim.

**Refinement our data should incorporate**: the -0.216 figure almost certainly conflates OC changes
with play-caller changes. Given how routinely head coaches retain play-calling over a new
coordinator (Stefanski, Shanahan, Coen, Moore, Sean Payton/Davis Webb are all documented above),
some fraction of our "new play-caller" rows are actually continuity. If so, the true play-caller
effect is *larger in magnitude than -0.216* and our current number is attenuated toward zero by
misclassification. That is a testable, directional prediction.

---

## Hypotheses for OUR league

Format: 10-team, full PPR, heavy volume and big-play bonuses, 4-round rookie draft, 3 taxi slots.

**H4.1 — Re-derive the play-caller feature as "who calls plays", not "who holds the OC title", and
expect our -0.216 to get worse.** The public record shows head coaches retaining play-calling over
newly promoted coordinators as a routine occurrence. If our current feature is coordinator identity,
a meaningful share of flagged "changes" are false positives that dilute the coefficient. Concrete
test: hand-label play-caller for the last five seasons, refit, and check whether the RB carryover
gap widens past -0.216. If it does, our current engine is *understating* the penalty.

**H4.2 — Apply the play-caller penalty asymmetrically by position, in the ratio the stickiness table
implies.** SumerSports' numbers give a principled prior for the relative magnitudes: WR/TE target
share ~0.70, QB EPA/att ~0.60, best RB rushing stat ~0.40, EPA/rush ~0. Our own three measured gaps
(RB -0.216 play-caller, pass-catcher QB-change -0.074) already sit in that ordering. The hypothesis
is that a single global "coaching change" discount is wrong and should be replaced by
position-specific discounts scaled roughly to (1 − stickiness).

**H4.3 — Carry forward the new play-caller's own multi-year RB-target-share and PROE percentile as
a prior on the incumbent's role, weighted above the incumbent's own prior year.** This is the direct
operationalization of the Kellen Moore finding. In full PPR with reception and volume bonuses, RB
target share is worth far more to us than to a standard-scoring league, so a caller with a bottom-
third RB-target-share history is a materially larger downgrade for our roster than for the market's.
That asymmetry between our scoring and market ADP is where the edge is.

**H4.4 — Use situation-adjusted (PROE-style) pass rate, never raw pass rate, when projecting a new
caller's tendency.** Anderson's result that "teams that run the ball the most are not necessarily
the run-heaviest teams" plus ETR's Petzing caution both say the same thing: raw pass rate is a game
script artifact. If our engine currently carries raw team pass rate forward, it is importing last
season's win-loss record disguised as a scheme tendency.

**H4.5 — Bound the size of the pass-rate adjustment at roughly ±8 percentage points, and expect
typical changes to be a small fraction of that.** Anderson's `sigma_mu = 0.18` puts the full 32-team
spread of team effects at about .52 to .69 around a .60 situational baseline. Any coaching-change
adjustment our engine produces that moves projected team pass rate more than a few points should be
treated as a bug, not a signal. This is a sanity check we can code as an assertion.

**H4.6 — Do NOT adjust expected pass rate for offensive quality.** Vignesh's replication found
passing and rushing quality each contributed 3% importance against situational variables. If our
engine has a term that makes good passing offenses "expected" to pass more, it is adding noise and
partially cancelling the very tendency signal we are trying to measure. Cheap to test by ablation.

**H4.7 — 2026 is a year to systematically discount volume-based projections league-wide.** With 21
new OCs and more than half the league changing play-callers, the fraction of our player pool sitting
behind a broken prior is unusually high. Practical consequence for a 10-team dynasty: this is a
buy-window on *continuity* — players whose play-caller is unchanged should be systematically
underpriced relative to their projection reliability, because the market prices projections, not
projection variance. Our engine can surface a "scheme continuity" flag as a tiebreaker in trade
valuation and start/sit.

**H4.8 — Test the "second year in the system" prior rather than assuming it.** PFF's Matt Ryan case
runs the wrong way (better in year one under a new OC, worse in year two, twice). This is one
player, but it means the widespread "wait for year two" heuristic is unverified. Testable on our own
data: split incumbent-usage carryover by years-with-current-play-caller and see whether year two is
actually better than year one.

**H4.9 — Pace is unmeasured and should be measured before it is modelled.** No allowlisted source
quantifies pace stability or its response to a coaching change, but ETR treats pace as one of the
two inputs to team volume. Since we already ingest nflverse play-by-play, computing
situation-neutral seconds-per-play by team-season and regressing on prior season with a
play-caller-change interaction is a small piece of work that would make us better informed on this
than any public source I could find. **Unsourced prior — verify empirically in Phase 2.**

---

## What could not be sourced

- **No study of pace or play volume response to coaching change.** Tried: searches restricted to
  4for4.com, footballoutsiders.com, sumersports.com, opensourcefootball.com, espn.com, pff.com,
  substack.com on pace stability, seconds per play, situation-neutral pace. Found only live stat
  tables (Sharp Football pace stats, nfelo team tendencies, RotoWire, teamrankings). Establish The
  Run's pace content is paywalled.
- **No before/after study of incumbent player usage under a new play-caller with effect sizes.**
  The closest thing in the corpus is Chmyz's collection of play-caller tendency examples, which is
  anecdotal by construction. Our own -0.216 / -0.279 numbers appear to be better evidence than
  anything published on an allowlisted domain.
- **Reddit unreachable.** A thread titled "Coaching Changes Are Quietly Wrecking Your Fantasy Team"
  surfaced in search with a snippet claiming "QBs take a major hit with new head coaches (avg: -2.0
  PPG)" and that "Even WRs and RBs decline slightly with offensive staff changes." Both
  firecrawl_scrape and WebFetch refused www.reddit.com, so the methodology, sample and definitions
  behind that -2.0 PPG figure could not be inspected. **I am explicitly not citing it as evidence**
  — it is recorded here only so a later pass knows the lead exists and knows it is unverified.
- **Paywalled or off-allowlist and therefore not used**: The Athletic's "21 NFL teams changed
  offensive coordinators" piece (nytimes.com), Fantasy Life's play-caller/scheme change articles
  (fantasylife.com), Draft Sharks' 2026 coaching-changes breakdown (draftsharks.com), nfelo's team
  tendencies page (nfeloapp.com). The 21-team figure is sourced above to Establish The Run instead.
- **No peer-reviewed source.** A Duke Sports Analytics project on NCAA head coaching changes
  surfaced (dukesportsanalytics.com, not allowlisted) and is college football rather than NFL in any
  case.
