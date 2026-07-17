# Sleeper War Room Product Audit - 2026-07-16

## Verdict

The 07-13 P0 trust blockers are genuinely fixed, and the analytics surface has roughly
tripled since then: market-anchored valuation, opponent-adjusted stats, price-history
intel, a 121-scenario eval harness, a recommendation feedback loop. The engineering is
real.

But the product has not kept pace with the engine. It has become an expert system with
no interface for understanding it. It computes north of 70 endpoints of opinionated
numbers and explains almost none of them. It organizes twelve pages by which engine
produced the data, not by which decision the GM is trying to make. It spends its best
visualization effort on the two pages you browse, and renders the pages you act on
every week as walls of unlabeled numbers.

Rob's own read going in - not enough visuals, no explanation of how to read anything,
no organizing plan that pulls the user toward the tools' value - is correct on all
three counts. They are symptoms of one root cause: **the app is organized around what
the backend computes, not around what the GM decides.**

The next phase should not be more engines. It should be an explanation layer, a
decision-first information architecture, and visuals where the weekly decisions
actually happen.

## What Works

- The 07-13 P0s are closed: current-season valuation, single replacement subtraction,
  validated trade IDs, correct pick ownership, `acceptance_score` instead of fake
  `93% YES`. Verified against current code, see "What The Last Audit Fixed" below.
- The Report Card page and the GM Profiles page are proof the team knows how to do this
  right: a real glossary with plain-English definitions and live league benchmarks, an
  `InfoTip` hover explainer, a d3-force trade network, a skill-vs-luck quadrant scatter.
  Nothing else in the app looks like these two pages.
- The OpsBar LIVE/OFFLINE indicator reflects true API reachability rather than being
  decorative, and `data_quality`/`warnings` degradation is surfaced on the
  safety-critical endpoints that have it (draft, findings, league, faab_market, trades,
  vegas).
- The eval harness and recommendation scoreboard are a real step toward the calibration
  the 07-13 audit asked for - 275 tests, 121 scenarios, a red-zone backtest that
  validates a prediction against held-out data rather than just re-checking arithmetic.
- Read-only-by-design is intact and now honestly represented: the README no longer
  promises confirm-gated Sleeper writes it doesn't have.

## P0 - The App Doesn't Explain Itself

### 1. The explainer pattern exists and is used on one page out of twelve

Evidence:
- `frontend/src/components/viz.tsx:24` - `InfoTip`, a reusable hover/tap popover.
- `frontend/src/routes/ReportCard.tsx:69-104` - `DIM_INFO`, `M`, and `GLOSSARY`: eleven
  metric definitions in plain English, with caveats and live league benchmarks,
  rendered as an on-page glossary.
- Grep confirms `InfoTip` is imported in exactly two files (`viz.tsx`, `ReportCard.tsx`)
  of the twelve route files.

Impact:
- Dashboard shows a `### FIT` badge (`acceptance_score`) with no scale stated anywhere.
- Waivers shows a color-coded priority bar with a hidden 0-100 threshold and never
  prints the number.
- Edges shows `EDGE %`, `VALUE GAP`, `MKT VAL`, leverage ratios, title-equity numbers -
  no legend, no tooltip, terse section subtitles only.
- Matchups shows an SoS "index" with hidden color thresholds (`sosColor`) and an
  unexplained "LINEUP UPSIDE +X".
- Market Signals shows blowout risk %, momentum %, FAAB p25/p50/p75/p90, schedule luck
  - zero explanatory text.
- Prospects shows a 0-100 `dynasty_prospect_score` bar whose scale is never stated in
  the UI, even though the type comment in `lib/api.ts:578` clarifies a caveat
  (`usage_rate` is not literal target share) that never reaches the user.
- The Player Profile drawer shows WOPR, target share, air-yards share, xFP residual,
  volatility, `pick_equivalent`, FPAR - advanced metrics with zero explanation.
- Draft Board is the one non-ReportCard exception: a footnote legend at
  `DraftBoard.tsx:574` defines FPAR, tiers, and STEAL/REACH thresholds. It proves the
  team knows the pattern. It was never copied anywhere else.

Fix:
- Promote `DIM_INFO`/`M`/`GLOSSARY` out of `ReportCard.tsx` into a shared
  `lib/glossary.ts`.
- Attach `InfoTip` to every scored/graded/percentage metric on all twelve pages.
- Replicate the Draft Board footnote-legend pattern on every dense table.

### 2. The engines compute explanations and then throw them away

Evidence:
- `model/trade_acceptance.py:399-402` - `_acceptance_score` computes
  `position_fit`, `margin_score`, `history_score`, and `window_score` as named
  components, sums them into a single int, and returns only the int plus a formatted
  rationale string. The components never leave the function.
- `model/dynasty.py:156` - `value_player` returns one float. No decomposition of
  current-FPAR contribution versus age-curve premium/discount.
- `market/blend.py` - `blended_value` returns `(value, market_valued: bool)`. The bool
  says *whether* the market moved the number, not *how much* or in *which direction* -
  which is the actually interesting story for a user deciding whether to trust a
  valuation.
- `model/trade_acceptance.py:401` - the `confidence` field is a score-band label
  (`"HIGH" if score >= 74`), not a measure of uncertainty. A GM with 0-2 logged trades
  and a GM with 8 logged trades can both show `HIGH` confidence if the arithmetic lands
  the same.

Impact:
- The frontend cannot show a "why" breakdown for any score because the API doesn't
  expose one. This is a backend gap, not a frontend gap - Phase 1 below starts here.

Fix:
- Return the acceptance-score component breakdown from the API, not just the sum.
- Return dynasty value as `{value, current_fpar_contribution, age_curve_adjustment}`.
- Return blend divergence (`market_value - model_value`, or a percent), not a bool.
- Replace the score-band `confidence` with an explicit label ("score band, not
  statistical confidence") until real uncertainty is computed, per 07-13 finding #5's
  spirit.

## P1 - The App Doesn't Organize Itself Around a Decision

### 3. Navigation is grouped by engine, not by decision, and two pairs of pages collide by name

Evidence:
- Sidebar nav (`Sidebar.tsx:20-33`): War Room, Market Edges, Matchup Lab, Market
  Signals, Draft Board, Roster, Trades, Waivers, GM Profiles, Report Card, Prospects,
  War Room Brief. Flat, twelve items, no grouping.
- "War Room" (`/`) and "War Room Brief" (`/narrative`) are near-identical names for
  unrelated pages. "Market Edges" and "Market Signals" are adjacent nav items with
  overlapping, hard-to-predict content split (mispricing/title-equity/TD-regression on
  Edges; Vegas/movers/FAAB-percentiles/schedule-luck on Signals).
- Every page's sidebar label differs from its own `<h1>` (e.g. nav says "Matchup Lab",
  page renders "MATCHUP LAB" - fine there, but "War Room Brief" renders "WEEKLY
  NARRATIVE"). The active-nav highlight is the only wayfinding signal.
- No 404/catch-all route (`App.tsx:110-123`) - an unknown path renders a blank pane.

Impact:
- Related analysis is scattered with no connective tissue: schedule luck lives on
  Signals, playoff SoS lives on Matchups, TD regression lives on Edges, xFP residual is
  buried in the player drawer. A user chasing one question has to visit three pages and
  remember which one has what.

Fix:
- Regroup navigation by workflow, not by engine: **This Week** (War Room, Matchups,
  Waivers, Trades) / **Market** (merge Edges + Signals) / **Franchise** (Roster, title
  equity, contention windows) / **League** (GM Profiles, Report Card) / **Draft**
  (Draft Board, Prospects).
- Rename "War Room Brief" to something that doesn't collide with "War Room" -
  "AI Briefing" is the plainest option.
- Add a 404 route.

### 4. Zero cross-page links; the app is twelve islands

Evidence:
- Grep and route review confirm no page links to any other page. The only in-app
  navigation between related data is the player/owner drawer, opened from row clicks
  on Roster/Waivers/Draft/Prospects/Owners.
- Dashboard's action-queue cards show a "command" as inert text
  (`Dashboard.tsx:254`), not a link to the page where you'd execute the thought.
- Edges flags a BUY/SELL verdict with no link into Trades. Waivers doesn't link a
  candidate to its price history on Market Signals, even though
  `api.playerPriceTrend` (`/market/price-history/{id}`) is already wrapped in the
  client (`lib/api.ts`) and simply never called from anywhere.

Impact:
- Every insight is a dead end. The user has to manually remember a flagged edge and
  re-find the player on the Trades page to act on it.

Fix:
- Wire the obvious links: BUY/SELL row -> Trades prefilled with that player; waiver
  candidate -> price-trend sparkline; action-queue card -> deep link to the page that
  explains it.

### 5. The core AI loop exits through a terminal, and the in-app version of it contradicts the automated one

Evidence:
- `Narrative.tsx:305-311` - a "HOW TO USE" list instructing the user to copy a prompt,
  paste it into a separate Claude Code session, and wait for a finding to appear.
- `Dashboard.tsx:647` - the empty findings-feed state literally shows the shell command
  `sffm finding <kind> --body '...'`.
- `.claude/skills/war-room-reason/SKILL.md` describes a materially better automated
  loop: fetch the briefing, reason, draft, self-critique with a fresh subagent, then
  post one verified document. The in-app Narrative page does not trigger this loop and
  skips the critique step entirely.
- `Trades.tsx:1150-1185` - "ANALYZE" on a built trade also just produces a prompt to
  copy into Claude Code, not an in-app verdict beyond a raw value delta.

Impact:
- The single most valuable feature in the product - the reasoned, self-critiqued AI GM
  update - is invisible inside the app itself and requires a developer workflow
  (terminal, Claude Code session) to use at all. A non-technical version of this
  product does not exist.

Fix:
- Either trigger the `war-room-reason` skill loop from the Narrative page directly (if
  the runtime allows invoking it server-side), or rewrite the page's instructions to
  match what actually produces the best output, and drop the shell-command language
  from empty states in favor of in-app affordances.

### 6. Nothing in the product expresses the weekly routine

Evidence:
- The only complete statement of "refresh -> run the AI GM -> read the action queue ->
  decide" is `.claude/skills/war-room-reason/SKILL.md`, a Claude Code skill file, not
  anything a dashboard user ever sees.
- `RefreshStatus.freshness` (`lib/api.ts:990-1004`) carries per-source mtimes and
  cached-season data - fetched by the OpsBar refresh button but never rendered. There
  is no "last refreshed 3h ago" anywhere in the UI.

Impact:
- A new user - or Rob on a random Sunday - has to reconstruct the intended cadence from
  scratch. The product doesn't tell you what to do first, or how current the numbers
  you're looking at actually are.

Fix:
- Add a weekly-routine strip to the War Room home page (refresh -> run AI GM -> action
  queue), and surface per-source freshness timestamps in the OpsBar using data that's
  already fetched.

## P2 - Visuals Are Inverted and the Toolkit Is Half-Installed

### 7. The best charts are on the pages with the lowest weekly decision value

Evidence:
- Chart-heavy: Report Card (scatter, 4x ranked bar, radar, bump chart, diverging
  bars) and GM Profiles (d3-force trade network, skill-vs-luck quadrant scatter, age
  pyramid). Both are pages you browse, not pages you act on weekly.
- Wall-of-numbers: Draft Board (60+ row table), Prospects (up to 200 rows, only a 3px
  inline bar), Waivers (table, one 3px priority bar), Market Signals (four dense
  tables). These are the pages a manager actually uses every week.

Impact:
- Effort is spent where dwell time is lowest.

### 8. Roughly fifteen visualization/interaction dependencies are installed and imported nowhere

Evidence (verified by grep across `frontend/src`):
- `recharts` - 0 imports (all charts are hand-rolled inline SVG in `viz.tsx` instead).
- `@radix-ui/*` (dialog, dropdown-menu, tabs, tooltip, separator, slot) - 0 imports
  (drawers/modals are hand-rolled).
- `@tanstack/react-table` - 0 imports (tables are hand-rolled `<table>` markup).
- `@tanstack/react-virtual` - 0 imports; the 200-row Prospects table and the 60+ row
  Draft Board table render unvirtualized despite the library being a dependency.
- `@dnd-kit/*` - 0 imports.
- `cmdk` - 0 imports. This one matches dead client state: the Zustand store exposes
  `commandOpen` (`store/useAppStore.ts`) that nothing reads, implying a command palette
  that was planned and never shipped.

Impact:
- Maintainability debt in both directions: the team hand-rolled tables, modals,
  tooltips, and lists while shipping the exact libraries that solve those problems, and
  the densest tables in the app aren't virtualized.

### 9. Two fully-built backend features have no UI at all

Evidence:
- `GET /intel/feed` (`api/routers/intel.py:17`) - an aggregated injuries, depth-chart,
  opportunity, and league-moves feed. Confirmed absent from `lib/api.ts` entirely; the
  Dashboard's "INTEL - FINDINGS" panel calls `/findings` instead, which is a different
  thing (AI-posted findings, not this aggregate).
- `GET /negotiation` (`api/routers/negotiation.py:20`) - a per-player, per-owner trade
  negotiation copilot brief. Confirmed absent from `lib/api.ts`. This is a natural,
  already-built fit for the Trades page.
- Wrapped in `lib/api.ts` but never called from any component: `api.faab` (per-owner
  FAAB budgets across the league), `api.matchups` (the weekly matchup endpoint - on a
  page literally called "Matchup Lab," which uses `/gameday` instead), `api.vegasPlayoffs`
  (playoff-week Vegas environment), `api.playerPriceTrend` (per-player price history -
  see finding #4), `api.playerEnvironment` (per-player stadium/weather splits).

Impact:
- Real, already-implemented analytical value is sitting behind the API with no path to
  a user.

Fix:
- Ship an intel panel on the War Room, a negotiation brief inside the Trades drawer,
  per-owner FAAB on GM Profiles, and price-history sparklines wherever a player is
  already rendered - the data is one call away in every case.

### 10. Zero responsiveness

Evidence:
- No Tailwind responsive prefixes (`sm:`/`md:`/`lg:`) and no `@media` queries anywhere
  in `frontend/src` (verified by grep). Fixed 200px sidebar with no collapse. Charts
  use `overflowX: auto` and a `widthFloor` instead of reflowing.

Impact:
- This is a desktop-only app for a product people check from the couch on Sunday
  mornings. On a phone it is a horizontally-scrolling mess.

Fix:
- Minimum responsive pass: collapsible sidebar, breakpoint-aware grids on Dashboard and
  Roster, and let charts reflow below a width threshold instead of scrolling.

## P3 - Trust Under the Hood Is Thinner Than the Surface Suggests

### 11. The eval harness detects change, not correctness

Evidence:
- `evals/harness.py` + `evals/scenarios.py` - 87 train / 34 holdout scenarios call the
  real engine functions with injected inputs and assert against expected values that
  were themselves derived from the engine's own current output. A ledger entry in
  `evals/runs/` literally shows a deliberately-broken taxi-discount change caught as
  `12/13` and then reverted - proof the harness is a regression detector.
- The one genuinely predictive check in the repo is `evals/backtest.py`: a red-zone
  vs. yardage expected-TD model, fit on 2024, evaluated out-of-sample on 2025, with a
  measured MAE reduction.

Impact:
- "87/87 pass" is compatible with every one of the ~40 hand-tuned constants below being
  wrong. The harness would only catch it if someone changed the constant and forgot to
  update the scenario.

Fix:
- Extend the backtest pattern (fit on one season, score out-of-sample on the next) to
  the age curves, the acceptance formula, and the season-sim odds - anywhere ground
  truth (realized outcomes) exists.

### 12. Roughly forty unvalidated constants sit under every valuation, trade, and title-odds number

Evidence:
- Age-curve constants (`model/dynasty.py:36-71`): peak age, decay rate, ascent rate,
  discount rate, 8-year projection horizon - the docstring calls them "empirical
  priors" but nothing in the repo fits them to data.
- Market blend (`market/blend.py:29-42`): a 65/35 market/model split and a frozen
  `FC_TO_DYNASTY_SCALE = 0.066`, labeled "2026-07 snapshot" - a point estimate that
  will drift as the market moves and nothing re-derives it.
- Trade acceptance (`model/trade_acceptance.py:399`): `42 + position_fit + margin_score
  + history_score + window_score`, clamped to `[5, 98]`, with hand-picked bonus tables
  like `{"OPEN": 15, "SELECTIVE": 8, "INSULAR": -4, "DORMANT": -12}`.
- `_SEASON_WEIGHTS = {2024: 0.35, 2025: 0.65}` (`model/valuation.py:326`) - hardcoded to
  specific years; will silently mis-weight every season going forward unless someone
  remembers to update it.
- Verdict thresholds scattered across `mispricing.py`, `regression.py`,
  `contention.py`, `wire_watch.py` - all hand-set, none backtested.

Impact:
- The UI presents integer FIT scores and exact percentage odds with a precision the
  underlying constants don't earn.

Fix:
- No single fix; this is the target of finding #11's extended backtest work. Start with
  the constants that already have the most usage - the acceptance formula and the
  market blend scale.

### 13. `owner_dossier.py` and `owner_history.py` - the backbone of every trade recommendation - have zero tests

Evidence:
- `model/owner_dossier.py` (340 lines) and `model/owner_history.py` (574 lines) have no
  dedicated test file. `market/dynastyprocess.py`, the sole fallback when the primary
  market source (FantasyCalc) fails, is also untested.

Impact:
- The single source of truth for "how will this GM react to this offer" - which feeds
  the trade-acceptance formula in finding #12 - has no regression protection at all.

Fix:
- Add fixture-backed tests for owner dossier construction and history aggregation
  before touching the acceptance formula further.

### 14. Some data sources fail silently to empty instead of registering as stale

Evidence:
- `nflverse/loader.py:316-401` - `load_injuries`, `load_pbp`, and `load_depth_charts`
  catch HTTP errors and return an empty DataFrame with only a log warning. They do not
  register in `_STALE_FALLBACKS`, which is the mechanism the rest of the codebase uses
  to surface degradation to the API and the briefing.
- `master.py` has 15 bare `except Exception` blocks that each degrade to a placeholder
  section - a genuine bug in any one of them is indistinguishable from a real data
  outage.
- On Edges and Market Signals specifically, a failed fetch renders the same empty-state
  text as "no data to show" - a user cannot tell an error from an empty result.

Impact:
- This directly contradicts the codebase's own stated discipline elsewhere (the
  `_STALE_FALLBACKS` registry, the `data_quality` envelope) - it's the one place the
  loud-failure principle isn't followed, and it's upstream of `news_feed`, `handcuff`,
  and `wire_watch`.

Fix:
- Register injury/pbp/depth-chart fetch failures in `_STALE_FALLBACKS` like every other
  loader. Give Edges and Market Signals a distinct error state from an empty state.

## What The Last Audit Fixed

| 07-13 finding | Status on 2026-07-16 |
|---|---|
| P0 #1 stale `DEFAULT_VALUE_SEASON` | Fixed - `config.py:47-50` pins it to `LATEST_COMPLETED_NFL_SEASON` and warns loudly if uncached |
| P0 #2 replacement subtracted twice | Fixed - `dynasty.py:179` uses `max(0.0, player.current_fpar)`, no second subtraction |
| P0 #3 trade analysis drops unknown IDs silently | Fixed - `trades.py:120-125` raises HTTP 400 with `missing_player_ids` |
| P0 #4 traded-pick endpoint inverted | Fixed - `trades.py:227` filters on `owner_id` correctly |
| P0 #5 fake `93% YES` acceptance labels | Fixed - renamed to `acceptance_score` throughout |
| P1 #6 read-only action queue | Partial - `act/plans.py` adds manual, non-mutating plans; no action-state/outcome logging yet |
| P1 #7 README over-promised execution | Fixed - README now correctly claims read-only |
| P1 #8/#9 fake start-sit confidence / shallow waivers | Partial - waiver depth-tier and contention-window adjustments landed; `data_quality` still not universal |
| P1 #10 pick market invents price from volume | Partial - still trade-frequency-based, but now honestly labeled `market_source: "trade-frequency"` as a fallback behind FantasyCalc |
| P1 #11 AI reasoning outside the product | Not closed - see finding #5 above; the in-app Narrative page still describes the old manual copy-paste flow and contradicts the automated skill |
| P2 #13 no CI, pyright fails | Not addressed - still no `.github/workflows/*` |
| P2 #14 test coverage too narrow | Addressed - 20 tests -> 275 tests, plus the 121-scenario eval harness the audit asked for |
| P2 #16 data degradation not first-class | Partial - `data_quality` exists on 4 of 37 routers, a bare `warnings` field on 2 more |

## The Fix Order

### Phase 1 - Explanation Layer

1. Backend: expose the acceptance-score component breakdown, the dynasty-value
   FPAR-vs-age-curve split, and the market/model blend divergence instead of
   collapsing them to a single number or bool (findings #2).
2. Frontend: promote `ReportCard`'s glossary into `lib/glossary.ts`; attach `InfoTip`
   to every scored metric on all twelve pages; copy the Draft Board footnote-legend
   pattern everywhere else (finding #1).
3. Relabel `confidence` as a score band until real uncertainty exists.

### Phase 2 - Information Architecture Restructure

1. Regroup navigation by decision workflow: This Week / Market / Franchise / League /
   Draft. Merge Market Edges and Market Signals into one Market page.
2. Rename "War Room Brief" to remove the collision with "War Room."
3. Wire cross-page links: BUY/SELL -> Trades, waiver candidate -> price trend, action
   card -> its source page. Add a 404 route.
4. Add a weekly-routine strip and per-source freshness timestamps to the War Room home
   page and OpsBar, using the freshness data that's already fetched.
5. Reconcile the Narrative page with the automated `war-room-reason` skill loop instead
   of shipping the manual copy-paste path as the in-app default.

### Phase 3 - Visuals Where Decisions Happen

1. Price-history sparklines on any player row (endpoint already exists and is
   unused).
2. FAAB percentile distribution, TD-regression diverging bars, edge distribution on the
   new Market page.
3. Virtualize the Draft Board and Prospects tables with the already-installed
   `@tanstack/react-virtual`, or remove the dependency if it's staying unvirtualized.
4. Minimum responsive pass: collapsible sidebar, breakpoint-aware grids.

### Phase 4 - Wire the Orphaned Backend

1. Intel feed panel on the War Room.
2. Negotiation copilot brief inside the Trades drawer.
3. Per-owner FAAB on GM Profiles; playoff Vegas and weekly matchups on Matchups;
   per-player environment splits in the player drawer.

### Phase 5 - Trust and Reliability

1. Register injury/pbp/depth-chart failures in `_STALE_FALLBACKS`; give Edges and
   Market Signals a distinct error state.
2. Test `owner_dossier.py`, `owner_history.py`, and `dynastyprocess.py`.
3. Extend the `data_quality` envelope past 4 of 37 routers.
4. Add CI (pytest, ruff, pyright, eval smoke run).
5. Extend the backtest pattern from the red-zone model to the age curves, the
   acceptance formula, and season-sim odds.

### Phase 6 - Debt Sweep

1. Remove the ~15 unused frontend dependencies, or start using them (recharts,
   radix, dnd-kit, tanstack-table, cmdk).
2. Consolidate the palette/token duplication across ~10 files into `viz.tsx`.
3. Unify the six-plus divergent name-normalization implementations across
   `valuation.py`, `rec_scoreboard.py`, `trade_acceptance.py`, `combine.py`,
   `cfbd/loader.py`, and `cfb_box.py` into one shared helper.
4. Fix the README's stale `sffm roster` description and document the five undocumented
   CLI commands (`history`, `draft`, `trade`, `startsit`, `trends`).

## Bottom Line

The engine is ahead of the product. Every phase above closes that gap in order of
leverage: explain what's already computed before building more IA, restructure the IA
before adding more visuals, add visuals to the pages that get used weekly before wiring
in more backend surface, and only then chase the deeper calibration work - because
none of it matters if the user can't tell what a number means or where to find it.

The app becomes a decision product, not a data product, when every page can answer:

1. What does this number mean, and on what scale?
2. Where do I go next with this insight?
3. How fresh is the data behind it?
4. How much should I trust it?
