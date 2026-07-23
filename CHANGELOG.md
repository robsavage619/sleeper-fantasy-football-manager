# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] — Edge analytics, market-anchored valuation, engine evaluation, and the decision-first UI

The layer that turns the scoring core into a decision engine: sixteen deterministic
edge engines, each with an API router and tests, all wired into the single master
war-room briefing so the AI GM reasons over them — plus the harness that tunes
their calibration and the briefing prompt against ground truth.

### Added

- **The arena — blind historical replay of every decision the engine makes.** The one
  eval that scores the whole product rather than a component, by replaying this league's
  real Sleeper history with no knowledge of the outcome at pick time. Ground truth needs
  zero synthesis: the matchup feed carries each roster, what the manager started, and every
  player's real points scored under league rules. Three surfaces:
  - *Start/sit* (`sffm eval arena`): a blind projector picks each lineup from prior weeks
    only, scored against actuals, vs the manager and the hindsight ceiling. The base engine
    trailed managers by ~7-9 points of optimal-capture; **availability levers** (injury-
    report gating from nflverse, and a box-score-absence discount — both point-in-time
    safe) cut the engine's dead-starter rate from ~1.3/wk to ~0.45 (near the human 0.3) and
    lifted capture to ~81% vs the managers' ~84%. The residual is a ranking/news ceiling; a
    forecast/league-last-4 blend was measured and rejected.
  - *Head-to-head* (`--h2h`, `--league`): would the engine have won more? Against a strong
    manager it ties at best; league-wide it out-manages ~1 of 10 rosters — because this
    league is strong and tightly clustered, sitting 3 points below the pack ranks near last.
  - *Waivers* (`sffm eval waivers`): the engine's top-3 blind pickup targets returned
    ~50-100% more than a random add (37-60% ranking capture) — real value where the decision
    is a pure ranking among many options.
  - *Trades* (`sffm eval trades`): preferred the more-productive side 7/10 (win-now lens,
    picks excluded, p=0.34 — suggestive, small-n).
  Every headline ships with a bootstrap CI or a sign-test p-value (`evals/stats.py`), and
  results append to an arena ledger for regression tracking.
- **In-house team Elo + QB adjustment** (`model/elo.py`) — computed live from the cached
  schedule (the FiveThirtyEight dataset is dead), validated out-of-sample (63% game
  accuracy, within ~5.7% of Vegas), wired into playoff strength-of-schedule where Vegas has
  no lines. QB-adjusted Elo was measured (+0.31%, marginal) and kept but not promoted.
- **League-specific mispricing** (`/mispricing`) — re-scores every player under the
  league's exact rules *and* under generic PPR, then ranks the buy/sell gap the
  national market can't see. Position-median normalization cancels league-wide
  scoring shifts, isolating the player-specific edge.
- **Monte-Carlo title equity** (`/season-sim`) — a seeded season simulator that turns
  roster strength into playoff and championship probability, re-basing trade
  evaluation onto Δ championship%.
- **Weekly player projections, and the first forward-looking layer in the engine.**
  Sleeper's undocumented GraphQL endpoint is the only source of projections (the REST
  v1 API has none): `model/projections.py` pulls rotowire's weekly component line and
  re-scores it under the league's own rules rather than trusting the provider's generic
  `pts_ppr` — measured on 2026 wk1, that generic number runs ~2.2 points high for QBs in
  this league and ~0 off for RB/WR/TE, so reading it straight would bake a positional
  bias into every start/sit call. Now the top projection source in the start/sit
  optimizer, replacing a season-to-date average (MAE 4.497 vs 4.768 out of sample).
- **In-house forecast engine** (`model/forecast.py`) — volume x efficiency with
  empirical-Bayes shrinkage toward positional priors (the shrinkage constant
  `k = within_var/between_var` is estimated from the season's data, not hand-tuned) and
  a Monte-Carlo simulation that scores every draw with the league's scoring engine.
  Because each draw is scored individually, threshold bonuses fire at their true
  probability instead of being rounded away by a mean stat line.
  **It does not beat the free projection** — MAE 4.739 vs rotowire's 4.497 over 4,069
  out-of-sample player-weeks, with the two sets of errors correlated at 0.935, so
  blending buys nothing either. Its value is the *distribution*: the provider ships one
  number per player, and a lineup decision needs a floor and a ceiling. It also stands
  as the fallback if the undocumented endpoint disappears (~5% worse, not zero).
- **Forecast backtest** (`evals/backtest.py::run_forecast_backtest`) — fits priors on
  one season and scores the next, against a season-to-date baseline, a last-4 baseline,
  and the provider. The comparison that produced the numbers above.
- **Contention-window classifier** (`/contention`) — labels every roster
  WIN-NOW / SUSTAIN / RETOOL / REBUILD / HOLD from odds + core age + youth share,
  with per-team buy/sell guidance for trade targeting.
- **Regression watch** (`/regression`) — touchdowns-over-expected flags for
  sell-high (rode TD variance up) and buy-low (unlucky on real usage) candidates.
- **Stadium & weather splits** (`/environment`) — historical FP by venue and
  conditions (dome / cold / wind / per-stadium) for start/sit tie-breaks.
- **Defense-vs-position + playoff strength of schedule** (`/schedule-strength`) —
  opponent-adjusted matchup ratings weighted to fantasy weeks 15–17.
- **Handcuff & leverage map** (`/handcuffs`) — exposed backups on the roster plus
  free-agent stashes sitting behind rivals' key starters.
- **Wire early-warning** (`/wire-watch`) — snap-share risers still available in the
  league, to get ahead of the waiver herd.
- **Gameday co-pilot** (`/gameday`) — pre-lock win probability and lineup upside.
- **Negotiation copilot** (`/negotiation`) — owner-tuned pitch (opening / walk-away /
  talking points) grounded in the counterparty's dossier.
- **GM's weekly address** (`/gm-address`) — a personality-rich "State of the
  Franchise" column built from the same briefing context.
- **Recommendation scoreboard, now graded against outcomes** (`/scoreboard`) — a
  living ledger of past recommendations that grades lineup and waiver calls against
  actual nflverse box scores (the started player outscored the benched one; a waiver
  add cleared a startable week), with the target week inferred from the schedule.
  Trade/draft/prospect calls stay honestly PENDING until they resolve. The graded
  hit-rate feeds back into the master briefing as a **GM Track Record** section so
  the model calibrates its own confidence, and renders on the Report Card page.
- **One-command refresh now covers the in-season feeds.** `POST /admin/refresh` and
  `sffm ingest` pull injuries, depth charts, play-by-play, and schedules — previously
  refreshed by neither — and `/admin/refresh/status` surfaces their freshness plus any
  stale-cache fallback.
- **Network resilience** — bounded retry with exponential backoff on every outbound
  fetch (Sleeper, nflverse, FantasyCalc, DynastyProcess), and a stale-fallback registry
  that turns a silent stale read into a surfaced signal in the status API and the
  briefing's data-freshness section.
- **Dashboard surfaces** — three new React routes, **Market Edges** (`/edges`),
  **Matchup Lab** (`/matchups`), and **Market Signals** (`/market-signals`), plus
  typed API client methods for every new endpoint.
- **Premium README, CHANGELOG, banner, and source-available license.**
- **Vegas game environment** (`/vegas`) — implied team totals and blowout risk from
  the spread/total, feeding a start/sit projection multiplier so a team implied
  well above or below league average nudges its players' weekly points.
- **Opponent-adjusted weekly scoring** (`/opponent-adjusted`) — re-weights weekly
  output for the strength of defense actually faced, on top of the raw box score.
- **FAAB market model** (`/faab-market`) — learns this league's *own* historical
  winning-bid percentiles by position from real waiver transaction history,
  replacing the generic 18%/10%/4% tiers with a league-grounded clearing price.
- **Price-history trend tracking** (`/market/price-history`) — dynasty value over
  time from archived market snapshots, surfacing top risers/fallers.

### Engine evaluation harness

A `sffm eval` CLI and Claude Code skill (`.claude/skills/engine-eval/SKILL.md`)
for tuning engine calibration and the master-briefing prompt against ground truth
— the train/test-split discipline applied to the app's own decision logic, not
just its code.

- **Tier 1 — deterministic scenario suite.** 121 scenarios (87 train / 34 holdout)
  across all 7 tunable engines (trade acceptance, dynasty valuation, FAAB pricing,
  waiver priority, start/sit lineup solving, mispricing verdicts, market-calibration
  rank correlation), each calling the real production function with hand-built,
  dependency-injected inputs — never a reimplementation. Every scenario's expected
  value is generated by running the actual engine, not derived by hand.
- **Tier 1 — out-of-sample backtest** (`regression.redzone_beats_yardage_oos`). The
  red-zone-opportunity expected-TD model is fit on one season and scored on the next
  from the cached play-by-play parquet, asserting its mean-absolute error is strictly
  below the yardage baseline — the reproducible measurement behind the docstrings'
  accuracy claim, run as a graded scenario.
- **Tier 3 — LLM-loop prompt evals.** Six hand-built briefing fixtures with planted
  traps (a hallucinated trade partner, a stale-data acknowledgment, a closed
  player universe, and three "the math checks out but the strategy doesn't" cases:
  a rebuild-window team trading a future pick for short-term production, a waiver
  priority score that ignores an actual roster hole, and a start/sit call that
  ignores a stated blowout/game-script risk) render through the real
  `build_master_briefing` template and grade the model's own reasoning — schema
  validity, closed-universe grounding, and FAAB bounds are fully scripted
  (`grade_doc.py`); an independent, fresh critic subagent judges whether a
  recommendation reconciles the acceptance-model math against the team's actual
  context, verified to genuinely discriminate sound from unsound reasoning rather
  than rubber-stamping.

### Changed

- **Expected touchdowns are priced by yard line, not by a binary red-zone flag.** The
  model split every target and carry on `yardline_100 <= 20`, so a carry from the 3 and
  one from the 18 were worth the same though they convert at roughly 39% and 4%. Each
  opportunity is now priced in its own yard-line bin (1-5, 6-10, 11-20, 21-40, 41+).
  Out of sample against the yardage baseline (fit 2024, scored 2025, n=235) the
  expected-TD MAE gain goes from **19.3% to 24.6%**; on the study's wider protocol
  (fit 2016-2023, scored 2024-25, n=511) the bins cut error 5.0% overall and 10.2% at
  running back, where touchdowns are goal-line events and the old bucket cost the most.
  The tier-1 eval floor is ratcheted from 5% to 20% so a revert to bucketing fails.
  Eight finer bin sets and three fitted continuous functions of `yardline_100` were
  scored on all nine consecutive-season splits first; none beat these bins by more than
  noise, and the smooth fits were clearly worse — see
  `docs/research/study-s5-yardline-weighting-2026-07-22.md`.

### Fixed

- **The recommendation scoreboard now actually grades.** Its extraction read the
  pre-fan-out document shape, so the per-item findings that `POST /findings/bulk`
  writes matched nothing and every rec sat PENDING forever. It now reads the
  fanned-out per-kind findings and joins lineup/waiver calls to real weekly outcomes,
  so the track record populates as graded weeks complete.
- **Substantiated the red-zone TD model's out-of-sample gain instead of asserting it.**
  The regression docstrings claimed a "~18%" expected-TD MAE improvement with no code
  behind it. A reproducible backtest (`evals/backtest.py`, fit on 2024 / scored on
  2025) measures **19.3%** across 235 players and runs as a tier-1 scenario; the
  docstrings now cite the eval and the measured figure. (That 19.3% was the binary
  red-zone model; yard-line bins later raised it to 24.6% — see Changed above.)
- **Refresh coverage holes closed.** Injuries, depth charts, play-by-play, and
  schedules were refreshed by neither `sffm ingest` nor `POST /admin/refresh` and had
  no freshness surface — they could go arbitrarily stale silently. All four are now
  covered and their mtimes reported; a fetch failure that falls back to cached parquet
  is recorded and surfaced rather than logged and forgotten.
- `load_weekly` now concats across the 2023/2024 nflverse schema boundary
  (`diagonal_relaxed`) so multi-season reads spanning the `player_stats` →
  `stats_player` format change no longer raise a `ShapeError`.
- **Trade engine now weighs the user's own contention window, not just the
  partner's.** The acceptance model only asked whether the partner would say yes;
  a rebuilding roster could be handed a "highest-FIT realistic offer" that spent a
  future pick on short-term production with no caveat. `_impact()` now penalizes
  and flags that mismatch directly, independent of the raw value margin.
- **Waiver priority now weighs actual roster construction.** The trend-based
  priority score couldn't distinguish a genuine positional hole from an
  already-four-deep position; it now applies a depth-tier adjustment
  (`+12` hole / `+6` thin / `0` normal / `-8` surplus) from the roster's own
  composition.
- **`MasterDocument`'s trade/waiver fields are now typed, not `dict[str, Any]`.**
  Found via the eval harness running against real model output: a FAAB bid
  formatted as `"$16"` and a multi-asset trade leg formatted as a JSON list both
  reached the API un-validated before. `faab_bid` is now a strict integer (a
  malformed string 422s); `send`/`receive` accept the list shape real output
  legitimately produces.

### A self-audit, then the decision-first pass it called for

A second product audit (`docs/product-audit-2026-07-16.md`) found the engine had
outgrown the interface: ~70 endpoints of opinionated numbers with almost none
explained, twelve pages organized by which engine produced them rather than which
decision they served, and two fully-built backend features (intel feed,
negotiation copilot) with no way to reach them. This entry is the fix, in the
order the audit prescribed — explain what's already computed, then restructure
the IA, then add visuals where decisions happen, then wire in the orphaned
backend, then the deeper reliability work.

**Explanation layer.**
- The acceptance-score and dynasty-value engines now return their component
  breakdowns instead of a single opaque number: `TradeOfferRecommendation`
  carries an `acceptance_breakdown` (base + roster-fit + value-margin + owner-
  history + contention-window + sample-size penalty), and `value_player_breakdown`
  splits dynasty value into current FPAR vs. age-curve adjustment vs. career
  phase.
- A shared `frontend/src/lib/glossary.ts` promotes the plain-English metric
  definitions that used to live only on the Report Card, and `InfoTip` — a
  reusable hover/tap popover, previously used on exactly one of twelve pages —
  is now attached to every scored metric across the whole app: FIT scores, waiver
  priority, edge %, strength-of-schedule index, blowout risk, FAAB percentiles,
  dynasty value, prospect score, WOPR/target-share/xFP residual.

**Decision-first information architecture.**
- Navigation regrouped by workflow instead of by engine: **This Week** (War
  Room, Matchup Lab, Waivers, Trades), **Market**, **Franchise** (Roster),
  **League** (GM Profiles, Report Card), **Draft** (Draft Board, Prospects).
- **Market Edges** and **Market Signals** merged into one tabbed **Market**
  page (Mispricing / Regression / Title & Contention / Vegas & Movers / FAAB &
  Schedule) — the split between them was arbitrary and nobody could predict
  which page held what. The old routes redirect.
- "War Room Brief" renamed to **AI Briefing** (it collided with "War Room" in
  the sidebar), and its copy now says plainly that it's a manual fallback —
  the real reasoning loop is the `war-room-reason` Claude Code skill, and its
  output shows up in the War Room's findings feed.
- Cross-page links where there were none: a Market BUY/SELL row now opens
  Trades with that player prefilled; a Waivers row links to its price trend;
  Dashboard action-queue cards deep-link to the page that explains them.
- A weekly-routine strip on the War Room (refresh → run the AI GM → read the
  queue → decide) and a "last refreshed Xh ago" indicator in the OpsBar, both
  using freshness data the app was already fetching and never displaying. Plus
  a 404 route — an unknown path used to render a blank pane.

**Visuals where the weekly decisions happen.** Price-history sparklines
(the endpoint existed, nothing called it), a FAAB percentile range chart and a
TD-regression diverging-bar chart on the Market page, the Prospects table
virtualized with `@tanstack/react-virtual` (Draft Board deliberately left
un-virtualized — its 60-row cap and sort-animation didn't justify the
rewrite), and a first responsive pass (collapsible mobile sidebar,
breakpoint-aware grids) on an app that had zero media queries.

**The orphaned backend, wired in.** Two fully-built endpoints had no frontend
path at all: `/intel/feed` now backs an Intel panel on the War Room, and
`/negotiation` now backs an expandable negotiation brief (opening / fair /
walk-away anchors, talking points) on every Trade Targets card. Per-owner FAAB
now shows on GM Profiles, playoff Vegas outlook and weekly matchups now show
on Matchup Lab, and per-player environment splits now show in the player
drawer — all five were already fetchable and simply never called.

### Reliability and debt

- **Injury / play-by-play / depth-chart fetch failures now register as
  stale**, not silently-empty. `load_injuries`, `load_pbp`, and
  `load_depth_charts` previously caught a fetch error and returned an empty
  frame with only a log line; they now register in the same
  `_STALE_FALLBACKS` mechanism every other loader in the module already uses,
  so a real outage is distinguishable from "no injuries this week." The eight
  routers backing Market Edges and Market Signals gained a `data_quality`
  field for the same reason.
- **`owner_dossier.py` and `owner_history.py` are now tested.** Both had zero
  coverage despite being the backbone of every trade recommendation; so did
  `market/dynastyprocess.py`, the sole fallback when FantasyCalc is down.
- **The out-of-sample backtest pattern — fit on one season, score on the
  next — is extended to the dynasty age curves.** The projected age-curve
  shape beats a naive flat-carry baseline by ~8% MAE with a 63% directional
  hit rate on real 2024→2025 data. The trade-acceptance formula and
  season-sim odds were evaluated for the same treatment; the honest finding is
  that no ground-truth dataset exists to validate acceptance against (the
  offer log tracks `sent`, not accepted/rejected/countered), so that gap is
  documented rather than papered over with a fabricated number.
- **CI**, for the first time: `.github/workflows/ci.yml` runs pytest, ruff,
  pyright, and a tier-1 eval smoke test on every push.
- **Six divergent name-normalization implementations** (`valuation.py`,
  `rec_scoreboard.py`, `trade_acceptance.py`, `nflverse/combine.py`,
  `cfbd/loader.py`, `college/cfb_box.py` each had their own) unified into one
  `src/sleeper_ffm/names.py`, which also fixed a latent asymmetric-join bug in
  `college/cfb_box.py` where the query side was normalized and the data side
  wasn't.
- **~10 of the ~15 unused frontend dependencies removed** (`recharts`, all of
  `@radix-ui/*`, `@dnd-kit/*`, `@tanstack/react-table`, `cmdk`) — installed,
  imported nowhere, while the team hand-rolled the tables, modals, and
  tooltips those packages exist to solve. `@tanstack/react-virtual` stayed;
  it's now actually used.
- Duplicated palette and component code (`POS_COLOR`, `SectionTitle`,
  `PosTag`, `Loading`/`Empty`) consolidated from ~10 route files into the
  shared `viz.tsx`.
- README's `sffm roster` description fixed (it described roster dynasty
  values; the command actually prints league-wide owner behavioral profiles),
  and the five previously-undocumented CLI commands (`history`, `draft`,
  `trade`, `startsit`, `trends`) are now documented.

---

## [0.1.0] — 2026-07-13 · Foundation

The base platform: a scoring-exact valuation core, a dynasty asset model, owner
intelligence, a draft assistant, and a React war-room dashboard driven by Claude
Code as the reasoning engine.

### Scoring & valuation
- League-exact scoring engine (stat line → fantasy points under the commissioner's
  real `scoring_settings`, threshold bonuses derived).
- Dynasty asset model — age-curve-projected FPAR with players, keepers, and three
  years of picks valued in one currency.
- Market-anchored valuation — FantasyCalc / DynastyProcess anchor with a rank-based
  model↔market blend (65/35), plus a pick market and draft-class-strength index.
- In-house sabermetrics — consistency, TD dependence, opportunity trend, age-curve
  residual, usage quality, and an uncalibrated xFP model.

### Owner & league intelligence
- Owner behavioral profiling and dossiers learned from the league's real transaction
  history (archetypes, approachability, trade-partner tendencies, positional needs).
- Owner skill / luck analysis (all-play win%, schedule luck, lineup efficiency).
- Trade-network graph and a grounded, acceptance-scored trade-offer engine.
- Historical manager report card and GM analytics across seasons.

### Draft & prospects
- Draft assistant with a live board, value-based recommendations, and a
  standings-based projected-slot convention for this league.
- Rookie prospect scouting fusing CFBD college data, combine athleticism, and market.

### Product & platform
- FastAPI backend, `typer` CLI (`sffm`), Polars data layer, nflverse ingestion.
- React / Vite / Tailwind dashboard with player-intelligence and prospect drawers.
- Reasoning loop — deterministic prompt-builders, a findings store, and the
  `war-room-reason` Claude Code skill (draft → self-critique → post).
- In-process scheduler keeping injury / depth / news feeds fresh.
- Recommendation-quality guardrails and a non-mutating evaluation endpoint.

### Guardrails
- Read-only by design: the app recommends, explains, and logs, but never submits a
  Sleeper transaction. No runtime LLM key in the backend.

[Unreleased]: https://github.com/robsavage619/sleeper-fantasy-football-manager/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/robsavage619/sleeper-fantasy-football-manager/releases/tag/v0.1.0
