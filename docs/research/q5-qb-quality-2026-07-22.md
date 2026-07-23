# Q5 — QB changes and pass-catcher production

Research date: 2026-07-22. Questions: does a receiver's target share survive a QB downgrade? How
much does QB quality (CPOE, EPA per dropback) move pass-catcher fantasy production?

Written directly against our own established result:

> QB changes were the MILDEST of three disruptions for pass catchers (carryover gap only -0.074).

Headline answer from the literature: **our finding is corroborated, but it is answering a narrower
question than it appears to.** Target *volume* does largely survive a QB downgrade. Fantasy *points*
do not, because points-per-target collapses. If our -0.074 is measured on usage, it is right and
also incomplete — the damage is on the efficiency side, which a usage-carryover metric cannot see.

---

## 1. The core decomposition: volume survives, efficiency does not

The best direct evidence in the corpus is a PFF study that split WR production by the tier of the
quarterback throwing to them, across all 32 teams and four seasons (2008–2011), separating targets
per game from fantasy points per target. Scoring was PPR for receivers.
(Chad Parsons, PFF, "Fantasy: QB Impact on Skill Positions, Part 2: WR Distribution", 2012-06-08,
https://www.pff.com/news/fantasy-qb-impact-on-skill-positions-part-2-wr-distribution)

**Fantasy points per game, by QB tier:**

| QB tier | WR1 PPG | WR1 avg rank | WR2 PPG | WR2 avg rank | WR3 PPG | WR3 avg rank |
|---|---|---|---|---|---|---|
| QB1–8 | 16.5 | 12 | 12.7 | 30 | 8.5 | 63 |
| QB9–16 | 14.9 | 18 | 9.9 | 47 | 6.4 | 85 |
| QB17–24 | 13.4 | 26 | 8.9 | 58 | 5.9 | 90 |
| QB25–32 | 11.3 | 40 | 8.4 | 64 | 5.6 | 93 |

Parsons: "There is a 32% drop in production between the top and bottom tier in terms of quarterback
play. The average No. 1 receiver with a top quarterback is a back-end WR1 in fantasy terms, while
the top target on a weak passing team would be fortunate to be a WR3."

**Now the decomposition, which is the actually useful part:**

| QB tier | WR1 tgt/g | WR1 FP/tgt | WR2 tgt/g | WR2 FP/tgt | WR3 tgt/g | WR3 FP/tgt |
|---|---|---|---|---|---|---|
| QB1–8 | 8.1 | 2.07 | 6.5 | 1.99 | 4.5 | 1.94 |
| QB9–16 | 7.8 | 1.90 | 5.6 | 1.82 | 4.0 | 1.62 |
| QB17–24 | 7.6 | 1.77 | 5.1 | 1.77 | 4.1 | 1.48 |
| QB25–32 | 6.9 | 1.66 | 5.3 | 1.61 | 4.1 | 1.43 |

Parsons' own reading, quoted: "The difference in usage is not a steep drop-off. No. 1 receivers with
a top-24 quarterbacks are between 7.6 and 8.1 TGT/G on average – a difference of just 8 targets over
a full season. The efficiency falls off at a greater rate than the volume when looking at the
different tiers. The TGT/G rates falls from the top-tier at a rate of 4% for No. 1 receivers, while
their FP/TGT falls 8% on average. The difference for No. 1 receivers in FP/TGT from the top-tier to
the bottom is a full 20%."

**This is the direct answer to "does target share survive a QB downgrade?" Yes.** Across the top
three quarterback tiers — 24 of 32 teams — a WR1's target volume moves only 8.1 → 7.6 per game, a
6% decline. Only the true bottom tier (QB25–32) shows a real volume hit, down to 6.9. Meanwhile
FP/target falls monotonically across every tier, 2.07 → 1.90 → 1.77 → 1.66, a 20% total decline
with no floor.

**Probability of a top finish, same study:**

| QB tier | WR1 top-10 | WR1 top-20 | WR2 top-10 | WR2 top-20 | WR3 top-36 |
|---|---|---|---|---|---|
| QB1–8 | 53% | 84% | 9% | 38% | 13% |
| QB9–16 | 38% | 59% | 0% | 3% | 6% |
| QB17–24 | 16% | 44% | 0% | 0% | 3% |
| QB25–32 | 3% | 22% | 0% | 0% | 0% |

The tail effect is far more brutal than the mean effect. A WR1 with a top-8 QB is a top-10 finisher
53% of the time; with a bottom-8 QB, 3%. That is a 17x swing in the outcome that actually wins
fantasy leagues, driven by a variable (target volume) that barely moved.

Parsons also settles the classic question: "The average No. 2 with a top-8 quarterback is a solid
WR3 in fantasy terms, while the No. 1 with a bottom-tier quarterback is 1.4 PPG lower and ranks 10
spots lower at the position." The WR2 on a good passing offense beats the WR1 on a bad one.

**Caveats, stated honestly and prominently.** This study is from 2012 on 2008–2011 data. It predates
the modern passing-volume era, the 11-personnel revolution, and the current alignment-based target
economy. The *structure* of the finding (volume sticky, efficiency not) is what should be carried
forward; the *magnitudes* should be re-derived on modern data. It is also tier-based rather than
continuous, and "WR1/WR2/WR3" is defined post hoc by within-team fantasy PPG rank, which induces
some selection. Nobody in the allowlisted corpus has published a modern replication — see the gaps
section.

---

## 2. QB identity redistributes targets by role, even when it does not change total volume

This is the modern nuance the 2012 study cannot capture, and it is where the real risk to a specific
roster lives.

Jake Tribbey computed three-year (2022–2024) positional target rates for every projected starting
QB. His framing: "QBs aren't just passengers in a system — they're the ones pulling the trigger...
Schemes matter, but QB preferences can reshape how those schemes play out."
(Jake Tribbey, Fantasy Points, "2025 QB Positional Target Tendencies", 2025-07-29,
https://www.fantasypoints.com/nfl/articles/2025/qb-positional-target-tendencies)

Observed spreads, all from that piece:

- **RB target rate**: Russell Wilson 26% vs Jameis Winston 11% — "There is no bigger difference in
  RB target shares between teammates." Anthony Richardson's 9.7% is "the single-lowest multi-year
  rate I've ever seen from a potential starter" in data going back to 2017.
- **Slot target rate**: Jameis Winston 37% vs Russell Wilson 27%. Tribbey converts this to volume:
  "that's the difference between 218 and 159 slot targets using New York's 2024 passing numbers."
  Fifty-nine slot targets is roughly a whole fantasy-relevant role appearing or disappearing on the
  same team, in the same scheme, from a QB swap alone.
- **WR target rate**: Matthew Stafford at 72% is the highest among established starters — "No player
  targets WRs like Matthew Stafford... which is why he has such a reputation as a WR kingmaker."
- **Backups differ systematically from starters**, and in a consistent direction: Tyson Bagent 23%
  RB target rate vs Caleb Williams 15%; Jarrett Stidham 25% vs Bo Nix 19%; Davis Mills 22% vs C.J.
  Stroud 14%; Jimmy Garoppolo 18% vs Matthew Stafford 11%; Mason Rudolph 28% TE target rate vs Aaron
  Rodgers 17%; Zach Wilson 21% TE rate vs Tua Tagovailoa 15%. Tribbey names the pattern: "Continuing
  this pattern of backups targeting RBs more often."

He also gives a clean, if single-player, before/after: **Jonathan Taylor averaged 1.3 targets per
game and 15.7 XFP/G (RB11) in his nine games with Anthony Richardson, but 3.6 targets per game and
19.5 XFP/G (RB1) in all other contests.** Same team, same season, same back — the QB changed and
the receiving role nearly tripled.

**What this means for our -0.074.** A study measuring *aggregate pass-catcher* usage carryover will
correctly find QB changes to be a mild disruption, because the team still throws roughly the same
number of passes to roughly the same set of people. But that aggregate conceals a redistribution:
slot moves to outside, WR moves to RB and TE, and individual players inside the group win and lose
badly. Our engine is likely averaging away real, tradeable signal.

Tribbey's two stated caveats apply and are worth carrying: the data "will be heavily skewed by
sample size and a QB's surrounding cast," and a QB who played with Travis Kelce will show a high TE
rate for reasons that are not about the QB.

---

## 3. What actually predicts pass-catcher production, and how much QB quality is in it

**Target share is the stickiest statistic in football.** SumerSports computed year-over-year
correlations since 2021 for players with 100+ snaps in consecutive seasons: target share ~0.70,
yards per route run >0.60, QB EPA per pass attempt ~0.60, sack-avoidance metrics ~0.50, best RB
rushing stat ~0.40, EPA per rush attempt "virtually negligible."
(Sam Bruchhaus, SumerSports, "Sticky Football Stats: Predictive NFL Metrics", 2025-07-14,
https://sumersports.com/the-zone/sticky-football-stats-predictive-nfl-metrics/)

Their reading is directly relevant: "Target share has a correlation around 0.70, which indicates
that wide receivers that are good enough to demand targets in their offense typically remain good
enough to demand more." And their worked example is *exactly our question* — they call Malik Nabers
a beneficiary specifically because "he had a very unstable quarterback situation last year and has a
three-man quarterback competition going into camp," i.e. they treat QB instability as something a
target-earner's usage survives.

Their summary advice: "Trust receiver rate stats, particularly if they are describing the player's
usage." And, importantly for the QB side: "Leverage EPA for quarterbacks but always take scheme and
team changes into consideration," with the caution that EPA "is technically a team statistic"
bundling the line, the receivers and the coordinator — "it is difficult to ever properly assign
credit solely to the quarterback for a team's offensive efficiency."

That last point is a live problem for any engine that uses EPA per dropback as a QB-quality input:
part of what we would be crediting to the new quarterback is the receiver we are trying to project.
The circularity is real and needs an explicit decision.

**The metric purpose-built for this question exists and we should probably use it.** PlayerProfiler
defines Target Premium as "the percentage of additional fantasy points per target that a wide
receiver or tight end generates over and above the other pass receivers on his team," and states
outright: "This metric is especially useful when examining the impact of a quarterback upgrade on a
wide receiver's future production."
(PlayerProfiler, "Advanced Stats Glossary of Terms", https://www.playerprofiler.com/terms-glossary/)

Because it is measured *relative to a player's own teammates*, Target Premium differences out the
quarterback almost by construction. That makes it the natural way to separate "this receiver is
good" from "this receiver has a good quarterback" — which is precisely the operation our valuation
engine needs when a QB change is announced.

---

## 4. On CPOE and EPA per dropback specifically

I could not find an allowlisted source that regresses pass-catcher fantasy points on CPOE or on EPA
per dropback and reports a coefficient. The pieces that exist:

- SumerSports gives EPA/attempt a ~0.60 year-over-year correlation for QBs, which bounds how much of
  a new QB's EPA we should carry forward as a forecast at all.
- Open Source Football hosts the nflfastR EP/WP/CP model documentation, including the completion
  probability model that CPOE is built from, with a reported expected-pass-model weighted calibration
  error of 0.008. (Ben Baldwin, Open Source Football, "nflfastR EP, WP, CP xYAC, and xPass models",
  https://www.opensourcefootball.com/posts/2020-09-28-nflfastr-ep-wp-and-cp-models/) That is the
  provenance of the metric, not a study of its fantasy effect.
- PFF's older QB/OC study concluded that coordinator shifts have "a relative minor correlation on
  what fans see on Sundays" (Aaron Resnick, PFF, 2017-07-18,
  https://www.pff.com/news/pro-qb-study-the-positive-and-negatives-of-shifting-a-quarterbacks-offensive-coordinator)
  — again about QB grade, not receiver output.

**No allowlisted source found** quantifying the marginal fantasy points a pass-catcher gains per
unit of QB CPOE or EPA/dropback. The PFF tier study above is the closest proxy and it uses fantasy
PPG rank as the QB-quality variable, not CPOE or EPA. Anything more specific I might assert about
CPOE elasticities is **unsourced prior — verify empirically in Phase 2**, and it is directly
computable from nflverse: regress receiver FP/target on the throwing QB's season CPOE and
EPA/dropback with player fixed effects.

There is one weak, uninspectable lead: a Reddit r/fantasyfootball post titled "[OC] How does QB
accuracy impact WR fantasy output?" surfaced in search with the snippet "WRs with a higher QBOT%
tend to score more fantasy points. WRs with inaccurate QBs perform worse on average than WRs with
accurate QBs." Reddit is unreachable via both firecrawl_scrape and WebFetch, so the method, sample
and effect size could not be checked. **Not cited as evidence** — logged only so a later pass knows
the lead exists and knows it is unverified.

---

## 5. Reading the corpus against our own numbers

**Our finding**: QB changes were the mildest of three disruptions for pass catchers, carryover gap
only -0.074.

**Corroborated on usage.** Two independent strands agree:
1. PFF's tier study: WR1 target volume is nearly flat across the top three QB tiers (8.1 → 7.6 per
   game, 6%), and only the true bottom tier moves it meaningfully.
2. SumerSports: target share is the stickiest stat in the sport at ~0.70, and they explicitly cite
   an unstable QB situation as something a target-earner's usage survives.

**Materially incomplete.** The same PFF study says fantasy points per target falls 20% top tier to
bottom, monotonically, with no flat region — and that the probability of a WR1 top-10 finish falls
from 53% to 3%. A usage-carryover coefficient of -0.074 is therefore consistent with a severe
fantasy-output effect, because the damage is entirely on the efficiency term our metric does not
measure. **If our engine reads -0.074 as "QB changes barely matter for pass catchers," it is drawing
the wrong conclusion from a correct number.**

**Also concealing dispersion.** Tribbey's role-level target rates (slot 37% vs 27%, RB 26% vs 11%,
WR 72% at the top) show that a QB swap redistributes targets sharply *within* the pass-catching
group. An aggregate carryover statistic averages this to near zero by construction. Our -0.074 may
be small precisely because the winners and losers cancel.

**Nothing found contradicts the -0.074 itself.** The contradiction is with the interpretation, not
the measurement.

---

## Hypotheses for OUR league

Format: 10-team, full PPR, heavy volume and big-play bonuses, 4-round rookie draft, 3 taxi slots.

**H5.1 — Split the QB-change adjustment into a volume term and an efficiency term, and put almost
all the weight on efficiency.** PFF's decomposition is unambiguous: 6% volume decline vs 20%
efficiency decline across the tiers where most teams live. Our engine should apply roughly no
penalty to projected target share on a QB downgrade and a substantial penalty to projected points
per target. Concrete test: refit our pass-catcher projection with FP/target as a separate,
QB-conditioned term and check out-of-sample improvement against the current single-coefficient form.

**H5.2 — In full PPR, the volume-survives result is worth MORE to us than to a standard league, and
the efficiency-collapses result is worth LESS.** Half of a PPR receiver's floor is the reception
itself, which is a volume event. A receiver whose target share survives a QB downgrade keeps a
larger fraction of his value in our format than in standard scoring. This is a direct, exploitable
asymmetry: the market prices QB downgrades using standard-ish intuitions, and we should be a
systematic *buyer* of high-target-share receivers whose QB just got worse. Testable by comparing
our own scoring's realized retention rate against the PFF-implied standard-scoring retention.

**H5.3 — Our big-play bonuses cut the other way and partially cancel H5.2.** Efficiency (FP/target)
is where the QB damage lands, and big-play bonuses are an efficiency multiplier. A downgraded QB
produces fewer deep completions, so our bonus structure amplifies exactly the term that degrades.
The net of H5.2 and H5.3 is an empirical question and is probably the single most valuable thing to
measure in Phase 2 for this question. **Unsourced prior — verify empirically in Phase 2.**

**H5.4 — Model the QB effect on receivers as a tail effect, not a mean effect.** The mean WR1 PPG
falls 32% top tier to bottom, but the probability of a top-10 finish falls from 53% to 3% — a 17x
change. In a 10-team dynasty where a league-winning receiver is the asset that matters, the
distributional collapse is the real cost. Our valuation should discount ceiling far more than median
when a QB downgrades. This maps cleanly onto the existing forecast floor/ceiling machinery.

**H5.5 — Add role-level QB target-rate priors (slot / outside / RB / TE) rather than a single
team-level pass-volume prior.** Tribbey's spreads (slot 27–37%, RB 9.7–26%, WR up to 72%) are large
enough to make or break an individual player's season inside an unchanged offense. Our -0.074
aggregate is almost certainly hiding this. Concrete implementation: for each announced QB change,
carry forward the incoming QB's three-year positional target rates and apply them to the incumbent
pass-catchers by their alignment.

**H5.6 — Treat backup QBs as a systematically distinct usage regime, not as "the starter but
slightly worse."** Six of Tribbey's backup/starter pairs show the backup with a materially higher RB
or TE target rate, and he names it as a pattern. Practical consequence for us: when a starter is
lost, our engine should *upgrade* the pass-catching RB and the TE and *downgrade* the outside WR,
rather than applying a flat team-wide haircut. In full PPR with reception bonuses, a check-down
backup is genuinely good news for a receiving back — this is a waiver-wire edge, and it is
week-one actionable.

**H5.7 — Use Target Premium (or a locally computed equivalent) to separate receiver quality from QB
quality before trading.** PlayerProfiler's metric is defined relative to a player's own teammates and
is explicitly recommended for exactly this purpose. If our trade engine values a receiver partly on
raw FP/target, it is paying for his quarterback. Building the teammate-relative version from our
existing data is straightforward and would sharpen every buy-low on a receiver stuck with a bad QB.

**H5.8 — Do not use raw EPA per dropback as a standalone QB-quality input without decomposition.**
SumerSports is explicit that EPA "is technically a team statistic" that bundles the offensive line,
the receivers and the coordinator. Using it to adjust receiver projections double-counts the
receiver's own contribution. CPOE is the more nearly QB-isolated of the two available metrics and
should be preferred if we use only one. This is a testable ablation: CPOE-only versus
EPA/dropback-only versus both, scored on receiver FP/target prediction.

**H5.9 — Re-derive the PFF tier table on modern data before trusting its magnitudes.** The 32% /
20% / 6% numbers come from 2008–2011. League-wide pass volume, personnel usage and the slot economy
have all changed. The structure should hold; the coefficients should not be imported. This is a
half-day job against nflverse and would give us a number nobody else has published.

---

## What could not be sourced

- **No modern replication of the PFF QB-tier study.** The best decomposition available is 14 years
  old. Tried: searches restricted to rotoviz.com, 4for4.com, fantasypoints.com, playerprofiler.com,
  establishtherun.com, pff.com, sharpfootballanalysis.com, footballguys.com,
  dynastyleaguefootball.com, substack.com for QB upgrade/downgrade effects on receiver fantasy
  points per target. Nothing comparable found.
- **No source quantifying pass-catcher production per unit of CPOE or EPA per dropback.** Searches
  restricted to opensourcefootball.com, arxiv.org, github.io, medium.com returned zero results;
  broader searches returned only definitional or descriptive content. This is the single cleanest
  gap and the most directly computable from data we already have.
- **Reddit unreachable.** "[OC] How does QB accuracy impact WR fantasy output?" (r/fantasyfootball)
  could not be retrieved by firecrawl_scrape or WebFetch. Its snippet claims a positive relationship
  between QB on-target percentage and WR fantasy points, but the sample, method and effect size are
  uninspectable. Recorded as an unverified lead, not as evidence.
- **Off-allowlist and therefore not used**: a Fantasy Footballers piece on how QBs perform after
  losing their WR1 (thefantasyfootballers.com), a Pitcher List correlation table of stats to PPR
  points (pitcherlist.com), and a Yahoo piece on college target share. The Pitcher List table in
  particular reports high raw correlations (targets 95%, air yards 91%, WOPR 83% to WR PPR points)
  but these are near-tautological same-season correlations with scoring inputs, not predictive
  findings, and the domain is not allowlisted — noted here only so a later pass does not chase it.
- **No peer-reviewed source.** None found on any allowlisted academic domain.
