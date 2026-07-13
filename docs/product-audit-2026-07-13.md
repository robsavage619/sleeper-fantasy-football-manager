# Sleeper War Room Product Audit - 2026-07-13

## Verdict

This is a strong personal dynasty cockpit, not yet a trustworthy decision product.

The best idea is the owner-aware war room: roster value, position ranks, age windows, pick
inventory, transaction history, and action recommendations in one place. That is a real
product spine. The app already helps Rob see the league better.

The brutal part: several recommendations are built on heuristics that look more certain than
they are. Some core data paths silently degrade. One core valuation path appears to subtract
replacement value twice. If that is true, the app's trade, roster, owner, and offer currency is
wrong by construction.

The next phase should not be more pages. It should be trust, calibration, and closed-loop
action.

## What Works

- War Room action queue is the right home screen. It turns league data into next moves.
- Owner dossiers are the most defensible edge: they combine current roster shape with
  historical behavior.
- Trade recommendations are partner-specific, not generic player rankings.
- Prospect fallback is honest in the UI when CFBD is unavailable.
- The app is better as Rob's personal league war room than as generic fantasy SaaS.

## P0 - Trust Blockers

### 1. Default valuation season is stale

Evidence:
- `src/sleeper_ffm/config.py` sets `DEFAULT_VALUE_SEASON` from the latest cached weekly parquet.
- Current local result: `DEFAULT_VALUE_SEASON 2024`, while `LATEST_COMPLETED_NFL_SEASON 2025`.

Impact:
- Roster values, draft board, trade analysis, owner dossiers, offers, and trends default to 2024
  production in a 2026 league context.
- A clean machine and Rob's current machine can produce different recommendations depending on
  local cache contents.

Fix:
- Make `DEFAULT_VALUE_SEASON = LATEST_COMPLETED_NFL_SEASON`.
- Add an explicit cache health endpoint showing available seasons, row counts, schema hashes,
  and generated timestamps.
- Fail visibly when required season data is missing.

### 2. Player valuation likely subtracts replacement twice

Evidence:
- `src/sleeper_ffm/model/valuation.py` computes:
  `current_fpar = season_fp - replacement`.
- `src/sleeper_ffm/model/dynasty.py` then computes:
  `base_fpar = current_fpar - replacement`.

Impact:
- Veterans are underpriced.
- Marginal but useful players can be zeroed out.
- Trade values, owner value ranks, roster strength, action queue offers, and draft decisions are
  all downstream of this currency.

Fix:
- Decide the invariant:
  - Either `PlayerAsset.current_fpar` means raw fantasy points and dynasty subtracts replacement.
  - Or `PlayerAsset.current_fpar` means points above replacement and dynasty must not subtract
    replacement again.
- Rename the field or add tests so this cannot regress.
- Rebaseline trade/roster outputs after fixing.

### 3. Trade analysis silently drops unknown player IDs

Evidence:
- `src/sleeper_ffm/api/routers/trades.py` filters requested IDs with `if pid in asset_map`.
- Missing IDs are excluded from values but the API still returns `ACCEPT`, `CLOSE`, or `DECLINE`.

Impact:
- A typo, missing crosswalk, or stale Sleeper player can flip a trade verdict.
- This is a premium trust killer.

Fix:
- Validate every requested player ID.
- Return `400` with `missing_player_ids` unless the request explicitly allows degraded analysis.
- Surface skipped assets in UI and findings.

### 4. Owned traded-pick endpoint is inverted

Evidence:
- `src/sleeper_ffm/sleeper/models.py` documents `roster_id` as original owner and `owner_id` as
  current holder.
- `src/sleeper_ffm/api/routers/trades.py` returns picks where `p.roster_id == MY_ROSTER_ID`.

Impact:
- `/trades/picks` can return Rob-originated picks, not picks Rob currently holds.
- Acquired picks can be excluded and traded-away picks can be included.

Fix:
- Use `p.owner_id == MY_ROSTER_ID` for currently held picks.
- Add fixture tests for own, acquired, and traded-away picks.

### 5. Confidence labels imply calibration that does not exist

Evidence:
- `src/sleeper_ffm/model/trade_acceptance.py` emits `93% YES` style output from a hand-weighted
  score.
- Formula is heuristic: base score plus roster fit, value margin, approachability, and window.

Impact:
- Users will read this as probability.
- It has not been calibrated against accepted, rejected, or countered offers.

Fix:
- Rename to `fit_score` or `acceptance_score`, not percent yes.
- Show it as `HIGH FIT`, `MED FIT`, or `LOW FIT` until calibrated.
- Add outcome logging: proposed, sent, rejected, countered, accepted.

## P1 - Product Gaps

### 6. The action queue is read-only

Impact:
- It tells Rob what to consider, but does not open the workflow, explain the downside, log
  decisions, dismiss stale actions, or track outcomes.

Fix:
- Add action states: `new`, `opened`, `sent`, `dismissed`, `accepted`, `rejected`.
- Every action card should open a decision drawer with rationale, data freshness, downside,
  counterfactual, and next step.

### 7. README promises execution that does not exist

Evidence:
- README references confirm-gated Sleeper writes.
- `src/sleeper_ffm/act/` and `src/sleeper_ffm/schedule/` only contain `__init__.py`.
- `src/sleeper_ffm/draft/assistant.py` references `act/playwright_driver.py`, which does not
  exist.

Impact:
- Product story and implementation diverge.
- Users may believe actions can be executed safely when they cannot.

Fix:
- Either remove the promise from README or build the confirm-gated action layer.
- Do not present submission/approval language in UI until the flow exists.

### 8. Start/sit can return fake confidence

Evidence:
- `src/sleeper_ffm/season/startsit.py` returns empty nflverse data on errors.
- It falls back to dynasty proxy or default `5.0`.

Impact:
- The app can return `200 OK` and recommend no changes based on defaults.

Fix:
- Add `data_quality` to responses.
- Fail hard if too many starters use default projections.
- Add projection MAE/regret evals before trusting this for lineups.

### 9. Waiver recommendations are too shallow

Evidence:
- Current priority is mostly trending adds, drops, age, and position.

Missing:
- Drop cost.
- Roster fit.
- Remaining FAAB.
- Opponent bidding tendencies.
- Role/injury/depth-chart context.
- Historical league clearing prices.

Fix:
- Build a waiver decision card: candidate, drop, bid range, downside, urgency, and why now.
- Backtest waiver candidates against subsequent roster percentage and points.

### 10. Pick market model invents price from volume

Evidence:
- `src/sleeper_ffm/model/pick_market.py` infers market value from trade count.

Impact:
- Trade frequency is not trade price.
- BUY/SELL can look analytical while being mostly arbitrary.

Fix:
- Parse actual assets exchanged in pick trades.
- Estimate implied pick prices from player/pick bundles.
- Show sample size and confidence.

### 11. AI reasoning is outside the product

Evidence:
- Narrative page tells Rob to copy a prompt into Claude Code.
- Findings can be arbitrary JSON and dashboard renders them raw-ish.

Impact:
- The core AI loop is not an integrated product loop.

Fix:
- Create structured decision records:
  - question
  - recommendation
  - edge
  - confidence
  - downside
  - missing context
  - action state
  - outcome

### 12. Draft board is a table, not a draft assistant

Missing:
- Tier breaks.
- Take-now vs wait recommendation.
- Probability a target survives to next pick.
- Trade-up/trade-down thresholds.
- Contingency plan for the next 3 likely picks.

Fix:
- Turn the draft board into an on-clock decision card plus board table.

## P2 - Engineering / UX Debt

### 13. No CI and full pyright fails

Evidence:
- No tracked `.github/workflows/*`.
- `uv run pyright` currently fails with 13 existing errors.

Fix:
- Add CI gates for Python and frontend.
- Fix or explicitly suppress pyright debt.

### 14. Test coverage is far too narrow

Evidence:
- 20 tests total.
- No API route tests.
- No mocked Sleeper tests.
- No frontend tests.
- No degraded-state tests.

Fix:
- Add frozen fixtures for Sleeper, nflverse, CFBD unavailable, and malformed trade inputs.
- Add FastAPI `TestClient` contract tests.
- Add frontend route smoke tests.

### 15. No recommendation eval/backtest harness

Missing evals:
- Valuation rank correlation.
- Start/sit regret.
- Waiver hit rate.
- Trade value calibration.
- Trade acceptance calibration.
- Pick market calibration.
- Owner-skill stability.

Fix:
- Create `evals/` with 50+ real scenarios stratified by simple, medium, hard.
- Track metrics over time.

### 16. Data degradation is not a first-class API concept

Impact:
- Fallbacks happen in isolated modules.
- UI cannot consistently communicate degraded data.

Fix:
- Add a shared response envelope for decision endpoints:
  - `data`
  - `data_quality`
  - `sources`
  - `warnings`
  - `degraded`
  - `generated_at`

### 17. Identity/config model is personal-only

Evidence:
- Backend hardcodes league/user/roster.
- Frontend hardcodes `MY_ROSTER_ID = 2` and `robsavage`.

Decision:
- If this is Rob's personal war room, keep it personal but centralize identity in one endpoint.
- If this is productized, build onboarding and league selection.

Recommendation:
- Keep it personal for now. Do not overbuild SaaS. But remove duplicated frontend constants.

### 18. Responsiveness and accessibility are incomplete

Evidence:
- Fixed sidebar and wide grid assumptions.
- Several clickable elements are `div`/SVG interactions without keyboard affordances.

Fix:
- Add mobile/tablet layout for draft/waiver moments.
- Convert clickable cards/nodes to accessible buttons or add roles, labels, and keyboard handling.

### 19. API/frontend contracts can drift

Evidence:
- Frontend types are manually maintained in `frontend/src/lib/api.ts`.

Fix:
- Generate a typed client from OpenAPI or add schema snapshot tests.

### 20. Latency is acceptable but not premium

Observed:
- `/trades/offers?top=5`: about 4.34s warm.
- `/war-room/actions?top=12`: about 4.48s warm.
- Most other endpoints: sub-second.

Fix:
- Build shared league context once per request.
- Cache owner dossiers/history/value maps.
- Add data freshness display.

## The Fix Order

### Phase 1 - Stop Lying

1. Fix default valuation season.
2. Fix replacement double-subtraction.
3. Fix traded-pick ownership.
4. Validate trade player IDs and pick IDs.
5. Rename percent-style acceptance labels to heuristic fit labels.
6. Add `data_quality` and warnings to action/trade/start-sit/prospect endpoints.

### Phase 2 - Make The App Useful In A Decision Moment

1. Replace static action cards with decision drawers.
2. Add action states and outcome logging.
3. Build waiver decision cards with drop/bid/risk.
4. Build draft on-clock decision cards.
5. Wire trend signals into trade and waiver actions.

### Phase 3 - Make It Trustworthy

1. Add CI.
2. Fix pyright.
3. Add API contract tests.
4. Add fixture-backed degraded-state tests.
5. Add recommendation evals/backtests.
6. Add cache/data health endpoints.

### Phase 4 - Make It A Cheat Code

1. Owner negotiation memory.
2. Trade offer outcome calibration.
3. Waiver bid clearing-price model.
4. Pick trade implied-price model.
5. Counterfactuals on every recommendation.
6. Closed loop: recommend -> act -> outcome -> learn.

## Bottom Line

Do not build more surface area yet.

Fix the value currency, expose data quality, and close the action loop. The app becomes useful
when every recommendation can answer:

1. Why this move?
2. What data supports it?
3. What is missing or degraded?
4. What is the downside?
5. What is the best alternative?
6. What happened after we acted?

