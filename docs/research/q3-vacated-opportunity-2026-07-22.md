# Q3 — Vacated opportunity: does it redistribute, and to whom?

Research date: 2026-07-22. This is the weakest-sourced of the three questions and the file says so explicitly.
Read it against our own empirical finding that vacated target share explained only ~3% of an incoming
receiver's usage (r = 0.18), and that a running back's prior target share explains ~17% of new usage after a
team change versus ~48% for a back who stays.

## Headline answer

**No allowlisted source published a quantitative model of vacated-opportunity redistribution.** The literature
that exists on the allowlist attacks the question sideways, through role and archetype, and what it says is
consistent with our near-null: opportunity attaches to a *role slot* that the coaching staff controls, not to
a queue position that the next man inherits. Two off-allowlist sources make the null claim explicitly, but
could not be read and are flagged as unverified.

The most useful allowlisted findings, in order of value to us:

1. Fantasy production is governed by which formation-role a receiver occupies, and the gap is large: lead
   receivers in two- and three-receiver sets average 11.5-12.6 PPR points per game while "everyone else is at
   8.0 or less" (PFF).
2. Role assignment is loosening over time, which makes depth-chart succession *less* predictable than it used
   to be — the player lined up at X was the team's lead X on 68.7% of plays in 2014 and 65% in 2023 (PFF).
3. Designed targets — the most explicitly coach-allocated opportunity type — are *less* sticky to players than
   ordinary targets (0.629), "reflect[ing] the additional control coaches exert over them, especially when
   players are paired with new play callers" (Fantasy Points). Opportunity of this kind belongs to the
   play-caller, not the player.
4. A documented succession case with measured efficiency collapse: Austin Ekeler took Melvin Gordon's touches
   in 2018 (17, 18 and 17 touches in the three games Gordon missed, versus 3, 9 and 9 for Justin Jackson) and
   his yards per touch fell from 8.1 to 3.9 (Sharp Football).

## What the allowlisted sources actually say

### Role, not depth chart, is what governs receiving opportunity

Nathan Jahnke, "Fantasy Football: Studying wide receiver utilization", PFF, 2024-07-03,
https://www.pff.com/news/fantasy-football-studying-wide-receiver-utilization

Jahnke defines X (split end, line of scrimmage, opposite the tight end, does not motion), Z (flanker, off the
line, often to the tight-end side) and S (slot) using PFF alignment data, rolls play-level positions up to
game and season level, and reports fantasy production by role since 2014.

The quantified findings:

- "the most important factor is being a lead player in both two and three-receiver sets, as they average
  11.5-12.6 PPR points per game while everyone else is at 8.0 or less."
- "X receivers tend to play better than Z receivers by a few percentage points across the board."
- The best PPR archetype is X in two-receiver sets *and* slot in three-receiver sets. Jahnke names the entire
  historical population of players who held it for meaningful stretches: Keenan Allen 2017-2020 ("the only
  receiver to maintain this role for several seasons"), Doug Baldwin, Larry Fitzgerald, CeeDee Lamb and Adam
  Thielen.
- Being a pure slot receiver without a two-receiver-set role is close to disqualifying: "Over the past decade,
  only five wide receivers have more than four games as a WR30 or better and as the team's slot receiver
  without being a lead player in two receivers" — Golden Tate 2017, Dede Westbrook 2019, Curtis Samuel 2020,
  Hunter Renfrow 2021, Wan'Dale Robinson 2023.
- Roles have physical signatures: X receivers are "taller and heavier with longer arms and hands in addition
  to better bench press repetitions but are slower than the Z receivers. S receivers are typically the
  smallest of the group," matching combine averages over the last decade.

**The one explicit succession case in the article:** "Lamb took over the X role from Amari Cooper after he
left before 2022." That is a role inheritance by archetype match — Lamb was already on the roster and
already the physical/route profile for the slot, and moved into the vacated X duties in two-receiver sets.
It is one anecdote, not a study, but it is the shape the mechanism takes.

**The finding that most complicates depth-chart-based inheritance:** role rigidity is declining. "In 2014, the
player at X receiver on a play was the lead X receiver from two- or three-wide receiver sets on 68.7% of
plays. That stayed pretty consistent until 2018, when that rate steadily declined by a few percentage points.
That dropped to 65% in 2023 with a notable dropoff from 2022 to 2023." Jahnke's summary: "Distinctions between
X, Z and slot receivers can still generally be made ... but it's less important than it was a decade ago."

If the roles themselves are getting fuzzier, then any redistribution model keyed to "who is the new X" is
modelling a target that is itself moving.

### Coach-allocated opportunity does not follow the player

Ryan Heath, "Statistically Significant: Designed Targets", Fantasy Points, 2025,
https://www.fantasypoints.com/nfl/articles/2025/statistically-significant-designed-targets

Heath reports designed targets at a year-over-year stickiness of 0.629 and draws the relevant conclusion
directly: "Notice that designed targets (0.629, above) are less 'sticky' for players than regular targets;
this reflects the additional control coaches exert over them, especially when players are paired with new play
callers."

He also gives a concrete example of a play-caller change reallocating a role wholesale: "Kamara received a
whopping 56% of the Saints' screen targets last year ... New Saints HC Kellen Moore has always spread out his
designed looks; no player under Moore has seen more than 35% of their team's screen targets since 2021."

And a note that talent does not determine who gets the role: "a player doesn't necessarily have to be a good
separator to earn them. Some play callers intelligently dole out these easy-button touches to their most
dynamic players after the catch, but others give them to Wan'Dale Robinson instead of Malik Nabers."

This is the strongest allowlisted evidence for the mechanism behind our r = 0.18. Some meaningful share of a
departing player's targets was never his — it was the play-caller's allocation to a slot. When the player
leaves and the play-caller stays, the slot may persist; when the play-caller changes, the slot itself
dissolves. A model that treats vacated targets as a transferable quantity is modelling the wrong object.

### Running back succession: the volume transfers, the production does not

Rich Hribar, "Fantasy Football Notebook: RB Correlations, Usage, and Archetypes", Sharp Football Analysis,
2019-07-31, https://www.sharpfootballanalysis.com/fantasy/fantasy-notebook-rb-correlations-usage-and-archetypes/

The documented Ekeler case, quoted:

> "Ekeler also had 17, 18, and 17 touches in the three games he was active that Gordon missed in 2018, while
> Justin Jackson tallied three, nine, and nine touches in those games. The downside is that Ekeler was not the
> same player in his extended role, turning his 52 touches in those games into just 205 yards from scrimmage
> (3.9 yards per touch). He averaged 8.1 yards per touch otherwise."

Hribar's generalisation: "it wouldn't be the first time that we've seen a hyper-efficient satellite back lose
efficiency with increased volume."

This is the single most useful datapoint in the file for a redistribution model, because it separates two
things our engine currently conflates: **volume inheritance succeeded (the RB2 got the touches) while
production inheritance failed (efficiency more than halved).** A model that maps vacated carries onto the
backup and then applies the backup's historical yards-per-touch will overproject badly.

The archetype framework in the same article gives the reason. Hribar splits backs into rushing-dependent
(80%+ of career standard-scoring output from rushing: Gus Edwards 95.4%, Sony Michel 97.7%, Derrick Henry
89.6%, Nick Chubb 84.6%, and so on) and receiving-dependent (over half of career PPR points through the air:
Theo Riddick 83.0%, James White 81.9%, Duke Johnson 76.1%, Nyheim Hines 73.0%, Tarik Cohen 69.7%, Austin
Ekeler 61.8%). A receiving-archetype back inheriting a rushing-archetype back's workload is not receiving the
same opportunity at all, even if the touch count matches.

He also quantifies how rare complete backs are: in 2018, "there were just 10 running backs who ranked in the
top-24 at the position in each of snaps, touches, routes run, targets, and rushing attempts per game." So in
most backfields the departing player's workload is *already* a bundle of separable roles that will split
across multiple successors rather than transfer to one.

### Corroboration from the stickiness tables (see Q1 for full context)

- RB team target share year-over-year: 0.2533. WR team target share: 0.4013. (Hribar, Sharp Football, 2024
  editions — see the Q1 file for links and the r-versus-r-squared caveat.) Running back receiving usage is
  materially less persistent than receiver usage even without a personnel change, which is the same
  directional result as our own team-change split.
- SumerSports on rushers: "environment matters. A lot," citing Barkley, Henry and Jacobs changing teams in
  2024 as the illustration, and reporting that rushing stats "across the board, have some of the lowest
  year-over-year correlations." Source: Sam Bruchhaus, SumerSports,
  https://sumersports.com/the-zone/sticky-football-stats-predictive-nfl-metrics/

### How the industry actually forecasts this (no model, just projections plus judgement)

Eric Moody, "Fantasy football: Six players who benefit most from vacated targets and touches", ESPN,
2026-07-21,
https://www.espn.com/fantasy/football/story/_/id/49401787/espn-nfl-fantasy-football-advice-players-benefit-vacated-targets

Included for completeness because it is the mainstream treatment and it is explicitly not quantitative. The
method is: identify teams with high vacated volume, then name the player the projections already like. Moody's
reasoning chain for each pick is contract size, depth-chart position, scheme fit and coach change — the same
inputs a human would use, with no redistribution model behind it. The tell is the phrasing: "Pittman should
absorb a large share of them **based on our projections**" (emphasis added). The projections are the
authority; vacated targets are the narrative.

Its own cited successes and how they were actually resolved:

- Rico Dowdle's Dallas workload → Javonte Williams, **signed in free agency specifically to fill it**. 287
  touches, RB12. The team went out and bought the successor; nobody on the roster inherited it.
- Cooper Kupp's Rams targets → Davante Adams, again **signed specifically to inherit them**. 114 targets, WR9,
  behind Puka Nacua's 166.

Both of its named prior-year successes are external acquisitions, not internal promotions. If that pattern
holds generally — and it is two anecdotes, so it does not establish anything — then the reason vacated share
does not predict an incumbent's usage is partly that teams *replace* rather than *promote*.

### Off-allowlist sources found but not read

Both directly address the question and both appear to reach the null. Neither could be scraped under the
allowlist, so **their claims below are unverified and must not be cited as established:**

- "Vacated Targets & Predicting the Future in Fantasy Football", The Fantasy Footballers,
  https://www.thefantasyfootballers.com/articles/vacated-targets-predicting-the-future-in-fantasy-football/
  Search-result summary: "Lost targets are descriptive of what happened the previous season but not in the
  least bit predictive or prescriptive for the following year."
- "The Myth of Vacated Targets", Dynasty Football Factory,
  https://dynastyfootballfactory.com/the-myth-of-vacated-targets/
  Search-result summary: "Vacated targets aren't a sticky stat because targets aren't inherited, they're
  earned. A team needs to see that there is a viable receiving option."
- r/DynastyFF, "Are vacated targets actually predictive of future WR breakouts?",
  https://www.reddit.com/r/DynastyFF/comments/vk5m8j/are_vacated_targets_actually_predictive_of_future/
  Reddit is on the allowlist but unreachable through both available fetchers (firecrawl: "we do not support
  this site"; WebFetch: blocked for reddit.com). Search-result summary: "The general answer is that vacated
  targets don't really matter."

These three independently point the same way as our r = 0.18. That is encouraging but it is hearsay, and
this file treats it as such.

## What could not be sourced

- **Any published regression of vacated target share (or vacated carries) onto the successor's realised
  usage.** This is the exact question and no allowlisted source answered it with numbers. Searches tried:
  "vacated targets predictive study"; "vacated target share redistribution"; "target share redistribution
  injury replacement"; "vacated carries who inherits touches" — including runs restricted to pff.com,
  4for4.com, rotoviz.com, footballguys.com, fantasypoints.com, sharpfootballanalysis.com, establishtherun.com,
  dynastyleaguefootball.com, playerprofiler.com, opensourcefootball.com, substack.com and medium.com, and a
  separate run restricted to opensourcefootball.com, github.com, arxiv.org, medium.com, substack.com and
  github.io. The domain-restricted runs returned **zero results**.
- **Any head-to-head test of depth-chart order versus role/archetype match as competing predictors.** The
  archetype literature (PFF roles, Sharp archetypes) and the depth-chart literature (handcuff content) exist
  separately and have never, on the allowlist, been raced against each other.
- **Handcuff hit rates.** No allowlisted source quantified how often the nominal RB2 actually captures the
  RB1's workload when the RB1 is lost. The search surfaced only listicles and video content.
- **Whether redistribution differs by departure type** (free agency versus trade versus retirement versus
  in-season injury). Every source treats "vacated" as one bucket. Our own engine has the data to split this
  and nobody in the literature has.
- **Team-level conservation.** Nobody tested whether a team's total target share is conserved after a
  departure, i.e. whether the passing volume itself moves rather than the targets redistributing. This is a
  prerequisite question and it is simply absent.
- **Red-zone / high-value opportunity redistribution specifically.** Q2 established that near-end-zone
  opportunity is what drives touchdowns; nobody studied whether *that* subset of vacated opportunity
  redistributes differently from ordinary volume.

## Hypotheses for OUR league

10-team full-PPR dynasty with bonuses: 2.5 for a 100-yard game, 5.0 for 200, 2.5 per 40+ yard TD, 1.0 for a
20-carry game, 2.5 for 300 pass yards and for 25 completions. These are hypotheses for Phase 2.

1. **Our r = 0.18 is not an anomaly to be explained away — it is the expected result, and the literature
   supplies the mechanism.** Designed/scheme targets are less sticky to players than ordinary targets (0.629
   per Fantasy Points) precisely because the coach owns them. Role definitions are loosening year over year
   (68.7% → 65% per PFF). Both effects push the vacated-to-successor correlation toward zero. **Recommendation:
   keep the null, publish it in the briefing as a null, and stop treating vacated target share as a
   projection input.** This is the clearest instruction the corpus yields.

2. **Replace "vacated share" with "vacated role slot", and test whether the role version predicts better.**
   The testable version: instead of asking how much target share left, ask whether the departing player was
   the team's lead two-receiver-set participant, and whether any incumbent matches that archetype. PFF's
   numbers say the difference between holding that role and not is 11.5-12.6 PPR PPG versus 8.0 or less — a
   gap of roughly 4 points per game, which in our 10-team full-PPR league is the difference between a starter
   and a bench player. **Prediction: role-slot vacancy will out-predict raw vacated share by a wide margin.**
   This is the highest-value single test in Q3.

3. **Split volume inheritance from production inheritance in the model.** The Ekeler case is the proof: he
   inherited the touches (17/18/17 versus the RB3's 3/9/9) and his yards per touch fell from 8.1 to 3.9. Our
   engine should project the successor's *touches* from depth chart and archetype, and his *efficiency* from
   his own history **regressed hard toward positional mean**, not carried forward at his small-sample
   satellite-role rate. Any successor projection that multiplies inherited volume by prior efficiency is
   structurally biased upward.

4. **Our 20-carry bonus makes this bias worse, not better.** A 1.0 bonus for a 20-carry game is a threshold on
   exactly the quantity that redistributes most cleanly (carries) attached to the archetype that most rarely
   survives promotion (the satellite back given a bell-cow workload). **Prediction: in our format, the engine
   will systematically overvalue the pass-catching backup promoted into a lead role, because it credits him
   both the inherited carries and the volume bonus while his efficiency collapses.** Testable directly against
   our own transaction-grade history.

5. **Weight the play-caller, not just the personnel.** Heath's Kamara example — 56% of Saints screen targets
   under the old staff, a new head coach who has never given any player more than 35% since 2021 — is a
   coaching-change effect that dwarfs the personnel change. In a dynasty league where we hold players across
   coordinator changes, an offensive-coordinator change flag is plausibly a stronger usage-projection signal
   than a teammate departure. **Unsourced prior — verify empirically in Phase 2**: play-caller change explains
   more variance in a returning player's usage than any teammate departure does.

6. **Expect receiver vacancies to redistribute better than back vacancies, consistent with what we already
   found.** Team target share year-over-year is 0.4013 for WRs against 0.2533 for RBs in the Sharp tables, and
   SumerSports says environment dominates for rushers. Our own split (RB 17% across a team change versus 48%
   staying, receivers carrying) matches this. Nothing in the literature contradicts our finding; it simply
   never ran the team-change split, so it cannot confirm the specific numbers either.

7. **Test the external-replacement hypothesis, because it would explain the null cleanly.** Both of ESPN's
   cited prior-year vacated-opportunity successes were players *signed to fill the hole* (Javonte Williams for
   Dowdle's role, Davante Adams for Kupp's), not incumbents promoted. If teams typically buy the successor
   rather than promote one, then vacated share genuinely *should not* predict an incumbent's usage — the
   correlation is near-zero for a structural reason, not because the measurement is noisy. **Testable on our
   data: split successor cases into internal promotion versus external acquisition and check whether vacated
   share predicts usage within the internal-promotion subset.** If it does, our 3% figure is a mixture
   artefact and there is signal hiding inside it. If it does not, the null is real and final.

8. **Model the departing workload as a bundle, not a scalar.** Only about ten backs a season are top-24 in
   snaps, touches, routes, targets and carries simultaneously (Sharp, 2018 season). For everyone else the
   departing workload is already several separable roles — early-down carries, goal-line work, passing-down
   routes, screen game — and will split across successors. **Prediction: modelling vacated opportunity as a
   single number is the main reason our r came out at 0.18; decomposing it into at least carries, targets and
   inside-the-10 opportunity will raise explained variance even if no single component is strong.**

9. **Give the archetype-mismatch case a negative weight, not a zero weight.** The current implicit model
   probably says "vacated targets exist, incumbent may benefit." The literature says a slot-only receiver
   almost never becomes fantasy-relevant without a two-receiver-set role — five players in a decade with more
   than four WR30-or-better games. So an incumbent whose archetype does not match the vacated slot should be
   *downgraded* on the news, not left flat, because the team now has an unfilled role it will fill from
   outside.

10. **This is the question where our own data is ahead of the published literature.** There is no allowlisted
    quantitative study of vacated-opportunity redistribution. Our r = 0.18 on our own league's data is, as far
    as this search could establish, a more direct measurement of the question than anything publicly
    available. That argues for investing in the decomposition in hypothesis 8 rather than looking for more
    sources — the sources are not there.
