# Q6 — Age curves by position and by archetype

Research date: 2026-07-22. Questions: what do published aging curves say by position, and by
archetype/role within position (satellite vs workhorse back, slot vs perimeter receiver, early- vs
late-breakout tight end)? Plus breakout-age research for WR/TE.

Two-sentence summary of what follows. The position-level literature is unusually good — there are
four independent, quantitative, allowlisted studies that broadly agree, plus one that argues the
whole aging-curve framing is wrong and offers a better one. The archetype-level literature does not
exist: **no allowlisted source was found that publishes separate aging curves for satellite vs
workhorse backs, slot vs perimeter receivers, or early- vs late-breakout tight ends.** That gap is
documented at the end and is the most valuable thing Phase 2 could build.

---

## 1. The methodological warning that should shape how we use all of this

Three of the four studies below independently flag the same problem, and one of them refuses to
publish a conventional curve because of it. This belongs first, not in a footnote.

**Survivorship bias makes naive aging curves say the opposite of the truth.** Blair Andrews at
RotoViz shows that if you take the average PPR output of all fantasy-relevant WRs by experience
level, "more experience seems to be a positive signal," and by age, "Apart from 21-year-old rookies,
it would appear that older WRs have an advantage over younger WRs." His explanation:

> "the higher averages we're seeing for older veterans are almost entirely the effect of
> survivorship bias. The only WRs left in the league after, say, five seasons are those good enough
> to have stayed in the league that long."

He also gives a precise structural fact worth encoding: the fantasy-relevant WR population "starts
to decline at age 24," because "it's the last age at which the number of players entering the league
is greater than the number of players leaving the league."
(Blair Andrews, RotoViz, "Misconceptions About Wide Receiver Age Curves Create Opportunity",
2024-08-01,
https://www.rotoviz.com/2024/08/misconceptions-about-wide-receiver-age-curves-create-opportunity-3-redraft-and-3-dynasty-targets/
— free portion; the analysis past the introduction is paywalled.)

**Individual careers do not look like the average curve.** Andrews, on a sample of post-2016 WRs:
"individual receivers exhibit a wide variety of career arcs. Some, like D.J. Moore and Christian
Kirk, take several years to reach their peak level of performance. Some, like Darius Slayton, never
improve from their rookie seasons. Many, like Chris Godwin, D.K. Metcalf, and Diontae Johnson, have
a one-to-two year peak period in Years 2 and 3 before declining slightly."

**Ryan Heath names the second failure mode: the ecological fallacy.** "An average of a group may or
may not be a useful representation of any of the group's individuals... This is especially dangerous
if the data is not normally distributed." He then notes that fantasy football is governed by power
law distributions, not normal ones, so "we should always expect a Tom Brady, Tony Gonzalez, or
Jerry Rice-like talent to age more gracefully than a merely 'good-to-great' player."
(Ryan Heath, Fantasy Points, "Age Curves: When NFL Players Break Out and Fall Off", 2023-06-23,
https://www.fantasypoints.com/nfl/articles/2023/age-curves-when-nfl-players-break-out-and-fall-off)

Heath's concrete illustration is the one to keep: at RB Year 8, "it would be a flagrant example of
the ecological fallacy to assume Henry will score around 73% of the RB baseline in 2023 — because
most Year 8 RBs don't!" The distribution has become bimodal — "the extreme ends of this distribution
are just as (or more) populated than the middle."

**Every study's own caveat, stated by its own author**, is that this is a conditional statement:
Heath asks the reader to mentally prefix every data point with "among players who made it to that
year of their career."

---

## 2. The best available model: mortality tables, not aging curves

Adam Harstad's reframing is the most methodologically defensible thing in the corpus, and both
Heath and Scott Barrett explicitly defer to it.

His thesis: "The traditional thinking on aging is that it resulted in a steady and inevitable
decline. After digging through 30 years of NFL history, however, I found that the 'steady decline'
model did not accurately represent what was actually happening to players on the field. Instead, a
better way to think of player aging is as a stable equilibrium prone to dramatic, sudden, and
unexpected drops. **Players essentially remain productive until one day when they're not any more.**"

Why this sidesteps the bias: "the advantage of a mortality table model is that it's self-culling...
We're only comparing players to their peers once they actually reach that age. Jerry Rice is
probably not going to be representative of how a typical receiver will age… but once a receiver
reaches age 40 in the first place, we already know he's not a typical receiver."

**Wide receiver mortality table** (best-fit curve, top-50 retired fantasy WRs since 1985; DR% =
chance of catastrophic career-ending decline at that age; EYR = expected fantasy-relevant years
remaining):
(Adam Harstad, Footballguys, "Dynasty, in Practice: How Do Wide Receivers Age?", 2015-09-05,
https://www.footballguys.com/article/HarstadDiP17?article=HarstadDiP17)

| Age | 21 | 22 | 23 | 24 | 25 | 26 | 27 | 28 | 29 | 30 | 31 | 32 | 33 | 34 | 35 | 36 | 37 | 38 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DR% | 2.1 | 2.7 | 3.4 | 4.3 | 5.4 | 6.8 | 8.6 | 10.8 | 13.6 | 17.2 | 21.6 | 27.3 | 34.4 | 43.3 | 54.6 | 68.8 | 86.7 | 100 |
| EYR | 8.61 | 7.80 | 7.01 | 6.26 | 5.54 | 4.86 | 4.22 | 3.62 | 3.06 | 2.54 | 2.07 | 1.64 | 1.25 | 0.91 | 0.61 | 0.35 | 0.13 | 0.00 |

**Running back mortality table** (same method, top-50 retired fantasy RBs since 1985):
(Adam Harstad, Footballguys, "Dynasty, in Practice: How Do Running Backs Age?", 2015-09-05,
https://www.footballguys.com/article/HarstadDiP18?article=HarstadDiP18)

| Age | 21 | 22 | 23 | 24 | 25 | 26 | 27 | 28 | 29 | 30 | 31 | 32 | 33 | 34 | 35 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DR% | 3.3 | 4.3 | 5.6 | 7.2 | 9.3 | 11.9 | 15.4 | 19.8 | 25.5 | 32.9 | 42.3 | 54.5 | 70.2 | 90.3 | 100 |
| EYR | 6.68 | 5.91 | 5.18 | 4.49 | 3.84 | 3.24 | 2.68 | 2.17 | 1.70 | 1.29 | 0.92 | 0.60 | 0.33 | 0.10 | 0 |

The positional gap is the cleanest quantitative statement of "RBs age worse than WRs" in the whole
corpus. At 25: WR DR% 5.4 / EYR 5.54, RB DR% 9.3 / EYR 3.84. At 30: WR 17.2 / 2.54, RB 32.9 / 1.29.
An RB's death rate at any age roughly matches a WR's death rate three to four years older.

**Harstad's own five caveats**, all of which should travel with the tables into our engine:
1. Not a prediction about individuals — "if you had 1,000 receivers like Calvin Johnson, then you'd
   expect the average remaining fantasy-relevant career length from the sample to be about two and
   a half years."
2. The tables only apply to players "who we already have strong reason to suspect are probably
   pretty good" — second-contract types. Applying an EYR of 7.01 to an unproven 23-year-old
   sixth-rounder is a misuse.
3. Selection bias remains: "young receivers who looked amazing but flamed out quickly do not get
   included in the sample."
4. Data is 1985–2014. "I would not be surprised if these EYR numbers underestimated the remaining
   careers of 30+ year old receivers to some degree."
5. **RB-specific**: the RB table understates risk, because unlike receivers, backs do show "a small
   decline in the year before they fell out of fantasy relevance entirely," which the table does not
   model. His consequence: "backs who experienced a decline last year will be at greater risk of
   'dying' than the table predicts, while backs who held steady or improved will be safer than the
   raw numbers suggest."

That last point is directly actionable — it is a free interaction term (prior-year trend × age) that
the published table leaves on the floor.

---

## 3. Experience-based curves (Heath, Barrett) and age-based curves (4for4)

Two framings exist and they disagree in interpretable ways. Both are worth having.

### By years of experience

**Ryan Heath**, all players since 2000, restricted to those with multiple top-12 finishes (multiple
top-6 for TE), comparing each career year to that player's own career baseline
(https://www.fantasypoints.com/nfl/articles/2023/age-curves-when-nfl-players-break-out-and-fall-off):

- **RB**: "+42% increase in production from Year 1 to Year 2" on average. Years 2–6 are peak and
  largely flat. "Year 7 provides the first hint of a steep and precipitous decline toward
  irrelevancy. From Year 8 on, RBs are usually worse off than when they were rookies."
- **RB breakout timing**: "a plurality of the sample first 'broke out' as rookies. The vast majority
  did so at least by Year 2." Critically, the +42% is not universal — "those who broke out (finished
  top-12) in Year 1 did not improve at all in Year 2 – actually scoring slightly fewer fantasy
  points than they did as rookies on average (about 11.3 fantasy points less over a full season)."
  The Year-2 leap belongs to backs who did *not* already break out.
- **RB championship relevance**: "11 of the 12 most popular RBs on playoff rosters from 2017-2021
  were in their first, second, or third season."
- **WR**: "WRs typically underwhelm as rookies, before making a big leap in their sophomore season...
  Unlike at RB, WRs gradually improve through Year 5, their best season on average. A slow
  regression to the career baseline occurs in Years 6-9, with a sharper drop to rookie-level
  production occurring in Year 10." Year 11 is bimodal.
- **WR attrition inside the "good player" sample**: "Our sample size shrinks from 33 players in Year
  8 to just 25 in Year 10, meaning about one-quarter (24%) left the league in that timespan. And
  remember, I have only included multi-year top-12 producers – not random scrubs."
- **WR breakout timing, and it is drifting**: breakouts occur "overwhelmingly in Years 2 and 3." But
  "Year 1 accounted for just 7% of breakouts pre-2014, but 26% of breakouts since. Years 2 and 3
  each accounted for 36% of breakouts before 2014, but just 16% and 26% (respectively) from 2014 to
  today." He immediately warns these are small sub-samples. Still, the direction — rookie WR
  breakouts roughly quadrupling in share — is a real regime shift and is consistent with the rookie
  hit-rate data in Q7.
- **TE**: "The sophomore TE breakout is among the most powerful and reliable laws of fantasy."
  Peak seasons are Year 5 and Year 6; "A steep decline begins in Year 7," at which point the
  distribution "becomes a Lovecraftian abomination" — the Year 7 average of 152 fantasy points "isn't
  very close to how most of the players actually performed." Past Year 7, "TEs will survive or die
  entirely on the merits of their own talent and resilience, with their production largely
  untethered from an aging curve."
- **TE rookie vs sophomore, hard counts**: "only four rookie TEs since 2010 have averaged just 10+
  FPG (Jordan Reed, Evan Engram, Kyle Pitts, and Aaron Hernandez). 12 sophomores (about one per
  year) have done so over 8+ games."

**Scott Barrett** ran the same shape earlier, 2000–2018, players with at least one top-12 (top-6 TE)
season, comparing each career year to the player's own average
(Scott Barrett, PFF, "Aging curves: How years in the league impact flex players' fantasy potential",
2019-06-06,
https://www.pff.com/news/fantasy-football-aging-curves-how-years-in-the-league-impact-flex-players-fantasy-potential):

- **RB**: peak in Year 3; "After Year 7, they stop producing in line with their baseline average and
  begin to (quite visibly) fall off a cliff, returning averages of 90% in Year 8, then 73%, and then
  60%."
- **Rookie-year production by position**: RBs score "88% of their baseline average in rookie seasons,
  while those numbers sit at 63% for both wide receivers and tight ends." That is the cleanest
  single statement of why rookie RBs are immediately usable and rookie WR/TE generally are not.
- **WR**: 96% of baseline by the sophomore season; peak Year 3 (118%), near-peaks Year 5 (117%) and
  Year 6 (113%); "Year 10 is the first year wide receivers start falling short of their baseline."
- **TE**: rookie 63%, peak Year 3 (130%), second peak Year 5 (124%), roughly at baseline until Year
  9 when they "fall from 102% to 86%."
- Barrett criticises his own study and points at Harstad: "Perhaps the better way to study aging
  curves is by looking at a player's mortality rate, as Adam Harstad did." He also flags the
  Gonzalez/Rice tail problem explicitly.

**Note the disagreement**: Barrett puts the WR peak at Year 3 (118%) and Heath puts it at Year 5.
Barrett puts TE peak at Year 3, Heath at Years 5–6. Different samples (2000–2018 with ≥1 top-12 vs
2000–2023 with ≥2 top-12) and different eras. I am not averaging them. The honest statement is that
the WR and TE peak is a broad plateau somewhere in Years 3–6, and the studies disagree on where
inside it the maximum sits.

### By player age

**Tristan Bassett / 4for4**, every RB and WR with at least two top-12 half-PPR seasons over the past
25 years (TEs: two top-6 seasons), plotted by age rather than experience. This study was explicitly
built as an age-based complement to Heath's experience-based work.
(Tristan Bassett, 4for4, "Production Curves: Positional Breakouts, Prime Years, and Falloffs by Age",
2025-08-23,
https://www.4for4.com/2025/preseason/production-curves-positional-breakouts-prime-years-and-falloffs-age)

- **RB**: "a back's best year is at about age 26, but remains roughly at their peaks from the time
  they enter the league — no matter what age that may be — until the age of 28." Breakouts: "The
  most common breakout year for a back is their rookie year, with a declining likelihood of a
  breakout every year after. By the time a player's rookie contract is up, so is virtually any hope
  of a breakout. Only two players in our sample of 47 (Michael Turner and Thomas Jones) had their
  fantasy breakout come in their fifth year or beyond, **and both breakouts came after those players
  changed teams.**"
- **WR**: "rookie wide receivers typically perform at around 80% of their average production
  baseline... 93% [at 23] and 91% [at 24]... the average receiver enter[s] the prime around age 25
  and perform[s] at their absolute peak from ages 26-28... Age 29 tends to indicate the start of the
  decline, but these receivers are still typically producing above or near their career baseline
  roughly through their age-31 seasons. After steep declines in age 32 and age 33, receivers have
  typically become a shell of the players they once were, performing at 74% of their career
  baseline." Breakouts: "over 70% of breakouts coming in years 2, 3, or 4."
- **TE**: prime at age 26 on average, later than RB or WR, and Bassett attributes this to entry age
  rather than a different maturation curve — "the later breakout age is likely due in part to tight
  ends entering the league at an older age." Breakouts generally Years 2–4, and "just below 50% of
  the tight ends in our sample had their breakout year in their third or later year."
- **TE longevity is the standout finding**: "The players in our sample didn't begin to show any
  signs of regression until age 31, but even then were producing at a level close to their peak
  production through age 32. Even at age 34, our tight ends were producing at 89% of their career
  baseline." Against: "Running backs, for example, were already down to 40% of their baseline
  production by age 33." He notes the survivorship caveat himself — "only 10 players in our sample
  have played in an age-34 season."
- His summary on the folk rule: "That magic '30 rule' does not apply in the slightest" to tight ends.

**The mechanism behind RB decline, per 4for4**: "Athletes will naturally lose a step as they get
older. However, the biggest cause of this falloff seems to be the accumulation of injuries over
time. This is why a back who has a longer injury history is far more prone to a noticeable decline
in fantasy production in this age range." He operationalizes it with efficiency metrics — yards
before contact/attempt, yards after contact/attempt, attempts per broken tackle — as a case-by-case
override on the curve. That is the closest thing in the corpus to an archetype-adjacent adjustment,
and it is injury-history-based, not role-based.

### An independent, non-fantasy confirmation that position matters

Caleb Smith tested the null hypothesis that position has no effect on aging, using all players since
1978 sorted by a production-threshold decision tree. Result: "the p-value of the ANOVA test was
effectively 0. The most similar positions in terms of aging were QBs and Kickers, but the difference
between them was still significant at the 5% level (p = 0.0118)."

His distribution modes: RB 24, "Receivers" 25, QB 26, K 25. Tails: "no 500 yard rushers were older
than 37"; roughly "1% of Quarterbacks, 0.1% of Receivers, and no Running Backs" appear in their 40s.
He is careful to state the limit of what he showed: "We have not shown that 25-year-old Receivers
are better than 35-year-olds, only that there are more of them."
(Caleb Smith, Medium, "Impact of Age on NFL Player Performance: Does Position Matter? (Part 3)",
2022-03-29,
https://calebrsmith95.medium.com/impact-of-age-on-nfl-player-performance-does-position-matter-part-3-6c404f68f6d7)

Important limitation he states himself: "'Receivers' includes both Wide Receivers and Tight Ends.
Because of the missing position data, it was too difficult to separate these two groups." So his
result confirms position matters in general but cannot speak to WR vs TE, and certainly not to
archetype.

---

## 4. Consolidated position-level picture

| | Rookie-year output | Peak | Decline onset | Cliff | Most common breakout |
|---|---|---|---|---|---|
| RB | 88% of baseline (Barrett) | Yr 3 (Barrett) / Yrs 2–6 flat (Heath) / age 26, flat to 28 (4for4) | Yr 7 (Heath) / age 29 (4for4) | Yr 8–10: 90% → 73% → 60% (Barrett); 40% of baseline by age 33 (4for4) | Rookie year (4for4, Heath) |
| WR | 63% (Barrett) / ~80% (4for4) | Yr 3 118% (Barrett) / Yr 5 (Heath) / ages 26–28 (4for4) | Yr 10 (Barrett, Heath) / age 29 (4for4) | ages 32–33 → 74% of baseline (4for4); Yr 11 bimodal (Heath) | Yrs 2–3 (Heath, Barrett); >70% in Yrs 2–4 (4for4) |
| TE | 63% (Barrett) | Yr 3 130% (Barrett) / Yrs 5–6 (Heath) / age 26 (4for4) | Yr 7 (Heath) / Yr 9 (Barrett) / age 31 (4for4) | untethered from curve after Yr 7 (Heath); still 89% of baseline at age 34 (4for4) | Yr 2 (Heath, Barrett); Yrs 2–4, ~50% in Yr 3+ (4for4) |

Mortality-table cross-check (Harstad): at every age from 21 to 34, an RB's catastrophic-decline
probability is roughly what a WR's will be three to four years later.

---

## 5. Archetype: the gap

The question asked for satellite vs workhorse back, slot vs perimeter receiver, and early- vs
late-breakout tight end. **No allowlisted source publishes separate aging curves for any of these
three splits.** What I found instead, and its limits:

- **Slot vs perimeter WR.** The only substantive claim located was a Steelers Depot article
  referencing a PFF piece on the slot role extending the careers of aging receivers
  (steelersdepot.com, not allowlisted; the underlying PFF article was not located by URL). I am not
  citing it as evidence. Searches restricted to footballguys.com, rotoviz.com, 4for4.com,
  fantasypoints.com, playerprofiler.com, pff.com, dynastyleaguefootball.com, substack.com and
  establishtherun.com returned only the general position-level age-curve articles already used
  above. **No allowlisted source found.**
- **Satellite / receiving back vs workhorse back.** Searches on the same domain set returned nothing.
  A 2017 RotoUnderworld/PlayerProfiler dynasty guide PDF surfaced in general search with a table-of-
  contents entry for "Pass-catching running backs" and a note that "the overall running back
  positional age curve shows a more gradual…" — the snippet is truncated, the document is nine years
  old, and I could not read enough of it to cite responsibly. **No allowlisted source found.**
  Everything the corpus offers on within-RB heterogeneity is injury-history-based (4for4) rather
  than role-based.
- **Early- vs late-breakout TE.** No source splits TE curves by breakout timing. The nearest thing
  is 4for4's observation that TEs' later average prime age "is likely due in part to tight ends
  entering the league at an older age" — which is a hypothesis about entry age, not a tested split.
- **DynastyProcess and ffverse aging-curve analyses.** The task brief said public analyses exist.
  What I could verify on an allowlisted domain is the *infrastructure*, not an aging-curve study:
  the ffverse GitHub org (https://github.com/ffverse) hosting ffscrapr, ffsimulator, ffpros and
  ffopportunity, and the DynastyProcess open-data repository
  (https://github.com/dynastyprocess/data, described as "An open-data fantasy football repository,
  maintained by DynastyProcess.com"), which nflverse's nflreadpy lists as a data source. I did not
  locate a published DynastyProcess aging-curve write-up on an allowlisted domain; dynastyprocess.com
  itself is not on the allowlist. **Reported as infrastructure, not as a sourced aging-curve
  finding.**

Everything I might assert about archetype-conditional aging is **unsourced prior — verify
empirically in Phase 2**. It is also the single most tractable original study available to us: we
already ingest nflverse play-by-play with alignment and route data, so splitting the existing
curves by slot rate, by RB target share, and by breakout year is a data-shaping problem, not a
data-acquisition problem.

---

## 6. Breakout-age research for WR/TE (bridging to Q7)

The definitions and the WR findings are documented in full in
`q7-rookie-indicators-2026-07-22.md`; the aging-relevant points are:

- Breakout age is defined at the *start* of the college season in which a player first posts a 20%
  dominator rating (WR), or 15% (TE and RB). (PlayerProfiler, "Advanced Stats Glossary of Terms",
  https://www.playerprofiler.com/terms-glossary/)
- Breakout age is the strongest non-draft-capital predictor of WR NFL fantasy production, and team
  receiving-yard market share adds further value on top of it because breakout age is a threshold
  that discards magnitude. (DSnasty_ff,
  https://dsnastyff.substack.com/p/the-most-and-least-meaningful-stats-ce8)
- The composite rookie-WR-breakout profile is a college breakout age of 19.8 with a 33.9% peak
  dominator. (Apex Fantasy Leagues,
  https://apexfantasyleagues.com/what-does-a-rookie-wide-receiver-breakout-look-like/ — not
  allowlisted, surfaced with full text in search; lower confidence.)

The connection to this file is that *college* breakout age and *NFL* breakout year are different
variables and the literature does not link them. Nobody has published whether an early college
breakout predicts an early NFL breakout, a longer NFL career, or neither. That is a clean,
answerable question and it sits squarely at the intersection of Q6 and Q7.

---

## Hypotheses for OUR league

Format: 10-team, full PPR, heavy volume and big-play bonuses, 4-round rookie draft, 3 taxi slots.

**H6.1 — Replace any smooth aging-curve multiplier in our valuation engine with a mortality-table
formulation.** Harstad's argument is the strongest methodological claim in the whole research
corpus, and both Heath and Barrett defer to it. Concretely: value a player as (current production ×
survival probability path), not as (current production × a curve that declines smoothly). The two
give very different answers for a 30-year-old — the curve says "expect 85% of last year," the
mortality table says "17.2% chance of near-zero and otherwise roughly what he did." In a 10-team
league with shallow benches, that difference changes whether you can afford to hold him.

**H6.2 — Encode Harstad's RB trend interaction, which the published tables omit.** He states
explicitly that the RB table understates risk and that "backs who experienced a decline last year
will be at greater risk of 'dying' than the table predicts, while backs who held steady or improved
will be safer." A prior-year-trend × age interaction on the RB death rate is a free improvement over
the published numbers, and Harstad himself never shipped it.

**H6.3 — Our valuation should be steeper on RB age than the market and flatter on TE age.** The
positional asymmetry is stark and consistent across all four studies: RBs are at 40% of baseline by
age 33 while TEs are still at 89% at age 34 (4for4); RB death rate at any age matches a WR's three
to four years older (Harstad). In full PPR with volume bonuses a productive TE is a scarce
positional weapon in a 10-teamer, and the market applies the folk "30 rule" indiscriminately. Buying
28-to-31-year-old producing tight ends at a discount is a directly testable edge.

**H6.4 — Weight the RB rookie year far more heavily than the market does, and stop waiting for
Year 3 breakouts.** Barrett: rookie RBs score 88% of their career baseline against 63% for WR/TE.
4for4: the modal RB breakout is the rookie year, and only 2 of 47 broke out in Year 5+ — both after
changing teams. Heath: 11 of the 12 most popular RBs on 2017–2021 playoff rosters were in Years 1–3.
For our 4-round rookie draft this means a first-round NFL running back is immediately usable in a
way a receiver is not, and it argues for taking the back over the equivalently-graded receiver when
our team is contending. It argues the opposite when we are rebuilding — see H6.6.

**H6.5 — But do NOT apply the +42% Year-2 RB bump to backs who already broke out as rookies.**
Heath's finding is precise and counterintuitive: rookie top-12 RBs scored about 11.3 fewer points
the following season on average. If our engine applies a blanket sophomore-year uplift to running
backs, it is systematically over-projecting exactly the players our roster is most likely to own.
Cheap to fix, easy to test.

**H6.6 — Our taxi squad should hold receivers, not backs.** With only 3 taxi slots, the question is
which position most rewards being warehoused through a non-productive early season. WR: rookies at
63–80% of baseline, breakouts overwhelmingly Years 2–3, peak Years 3–5, EYR 7.0 at age 23. RB:
rookies already at 88% of baseline, modal breakout in Year 1, and a back who hasn't broken out by
Year 3 essentially never will. A running back who needs stashing is a running back who has already
failed the position's own test. This is a concrete roster-construction rule our engine can enforce.

**H6.7 — Test whether the rookie-WR-breakout regime shift is real in our own data, and if so
recalibrate our rookie-pick prices upward.** Heath: Year 1 was 7% of WR breakouts pre-2014 and 26%
since. That is a large change with a direct valuation consequence — if rookie receivers now hit
sooner, a rookie pick is worth more and the "wait three years" dynasty discount is stale. He warns
the sub-samples are small. Our own league history plus nflverse gives us an independent test.

**H6.8 — Build the archetype-conditional curves ourselves; this is the biggest available original
edge in the whole research set.** No public source splits aging by role. We have alignment, route
and target data. The three splits to run, in priority order for our format: (a) RB by receiving
share — in full PPR with reception bonuses, a satellite back's value is target-driven and targets
are the stickiest thing in football (SumerSports, ~0.70 target share YoY — see
`q5-qb-quality-2026-07-22.md`), so the plausible hypothesis is that receiving backs age materially
better than rushing backs and the market prices them on the generic RB curve; (b) WR by slot rate;
(c) TE by breakout year. **Unsourced prior — verify empirically in Phase 2.**

**H6.9 — Add the injury-history override that 4for4 describes, since it is the only within-position
heterogeneity anyone has published.** Their mechanism claim is that accumulated injury, not
athletic decline, drives the RB falloff, and their proposed diagnostics are yards before contact per
attempt, yards after contact per attempt, and attempts per broken tackle. All three are computable
from data we hold. This is a testable substitute for the archetype split until we build it.

**H6.10 — Model the late-career distribution as bimodal, not as a lower mean.** Heath is explicit
that at RB Year 8 and TE Year 7 "the extreme ends of this distribution are just as (or more)
populated than the middle." Our forecast machinery already produces floor and ceiling; the specific
change is that for old players the *variance* should widen sharply rather than the *mean* dropping
smoothly. In a 10-team league where the waiver pool is deep, the correct play with a bimodal aging
asset is different from the correct play with a smoothly declining one — you can absorb the zero.

**H6.11 — Never apply a curve to a genuinely elite player without widening the interval.** Heath's
power-law point: "we should always expect a Tom Brady, Tony Gonzalez, or Jerry Rice-like talent to
age more gracefully than a merely 'good-to-great' player." Harstad's tables are explicitly scoped to
"second-contract type players." Our engine should flag when it is applying an aging discount to a
top-decile producer and widen the uncertainty rather than mechanically marking him down.

---

## What could not be sourced

- **Archetype-conditional aging curves — none exist on any allowlisted domain.** Specifically
  searched for: satellite/receiving back vs workhorse back aging; slot vs perimeter receiver
  longevity; early- vs late-breakout tight end curves. Domain-restricted searches across
  footballguys.com, rotoviz.com, 4for4.com, fantasypoints.com, playerprofiler.com, pff.com,
  dynastyleaguefootball.com, substack.com, establishtherun.com returned only the position-level
  studies already cited. Two near-misses were found and deliberately not cited: a Steelers Depot
  article (not allowlisted) referencing an unlocated PFF piece on the slot role extending aging
  receivers' careers, and a 2017 RotoUnderworld/PlayerProfiler dynasty guide PDF whose truncated
  snippet mentions pass-catching running backs and a "more gradual" RB age curve.
- **No published DynastyProcess aging-curve analysis on an allowlisted domain.** The brief said
  DynastyProcess and ffverse have public analyses. I verified the open-data infrastructure
  (github.com/dynastyprocess/data, github.com/ffverse) but not an aging-curve write-up.
  dynastyprocess.com is not allowlisted, so if the analysis lives there it was out of reach.
- **RotoViz's actual age-curve findings are paywalled.** Blair Andrews' introduction — the
  survivorship-bias argument and the age-24 population inflection — is free and is cited above. The
  curves themselves, and the six named targets, sit behind a membership wall. Not reproduced.
- **Harstad's original mortality-table framing article** (HarstadMortalityTables) is referenced by
  both Heath and Barrett and its two positional follow-ups were retrieved in full; the framing piece
  itself was not scraped in this pass. Its URL is
  https://www.footballguys.com/article/HarstadMortalityTables?article=HarstadMortalityTables.
- **No TE mortality table.** Harstad published WR and RB; a QB/RB/WR set is referenced in another of
  his pieces (HarstadDiT40) but was not retrieved, and no TE table was located.
- **No link between college breakout age and NFL career length or NFL breakout timing.** Both
  variables are well studied separately; nobody has joined them.
- **Off-allowlist and therefore not used**: The Athletic's July 2026 piece on peak age by position
  (nytimes.com), Fantasy Life's WR-age article, Apex Fantasy Leagues' peak-WR-age piece
  (apexfantasyleagues.com, reporting an average peak WR season at age 26.9 and 79% of peak seasons
  before age 30 — consistent with 4for4 but not citable here), Statista career-length figures, and
  a Fantasy Footballers dynasty-TE lifecycle article.
