# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] — Edge analytics, market-anchored valuation, and engine evaluation

The layer that turns the scoring core into a decision engine: sixteen deterministic
edge engines, each with an API router and tests, all wired into the single master
war-room briefing so the AI GM reasons over them — plus the harness that tunes
their calibration and the briefing prompt against ground truth.

### Added

- **League-specific mispricing** (`/mispricing`) — re-scores every player under the
  league's exact rules *and* under generic PPR, then ranks the buy/sell gap the
  national market can't see. Position-median normalization cancels league-wide
  scoring shifts, isolating the player-specific edge.
- **Monte-Carlo title equity** (`/season-sim`) — a seeded season simulator that turns
  roster strength into playoff and championship probability, re-basing trade
  evaluation onto Δ championship%.
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
  docstrings now cite the eval and the measured figure.
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
