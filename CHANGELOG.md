# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] — Edge analytics suite

The layer that turns the scoring core into a decision engine: twelve deterministic
edge engines, each with an API router and tests, all wired into the single master
war-room briefing so the AI GM reasons over them.

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
- **Recommendation scoreboard** (`/scoreboard`) — a living ledger of past
  recommendations with deterministic grading where ground truth exists.
- **Dashboard surfaces** — two new React routes, **Market Edges** (`/edges`) and
  **Matchup Lab** (`/matchups`), plus typed API client methods for every new endpoint.
- **Premium README, CHANGELOG, banner, and source-available license.**

### Fixed

- `load_weekly` now concats across the 2023/2024 nflverse schema boundary
  (`diagonal_relaxed`) so multi-season reads spanning the `player_stats` →
  `stats_player` format change no longer raise a `ShapeError`.

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
