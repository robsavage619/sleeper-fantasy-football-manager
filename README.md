# sleeper-fantasy-football-manager

AI dynasty fantasy football GM for Sleeper. Scoring-aware valuation, a dynasty asset model
(players + keepers + 3 years of picks in one currency), owner behavioral profiling, and
**Claude Code as the reasoning engine** (deterministic engines build prompts → Claude Code
reasons → findings post back → dashboard renders). No runtime LLM key in the backend.

League: *The League* — 2026 dynasty, full PPR with bonuses, 10 teams, 1QB / no K / no DST.
The app is currently read-only: it recommends, explains, and logs decisions, but does not
submit Sleeper transactions.

Current recommendation surfaces include trade-fit scoring with owner-history evidence labels,
waiver claim cards with bid ranges/drop candidates/downside, draft decision cards, data-quality
diagnostics, player intelligence drawers, and a non-mutating recommendation eval endpoint.

## Layout

- `src/sleeper_ffm/scoring/` — the scoring engine (linchpin): stat line → fantasy points.
- `src/sleeper_ffm/sleeper/` — read-only Sleeper API client (+ dynasty history walk).
- `src/sleeper_ffm/nflverse/` — historical stats ingestion (`nfl-data-py` → parquet).
- `src/sleeper_ffm/model/` — valuation, trends, projections, player profiles, dynasty assets,
  pick market, owner profiles.
- `src/sleeper_ffm/prompts/`, `reasoning/` — prompt-builders + the findings store Claude Code writes to.
- `src/sleeper_ffm/act/`, `schedule/` — manual transaction plans + future confirm-gated actions.
- `frontend/` — React/Vite/Tailwind dashboard.

## Dev

```sh
uv sync
uv run pytest
uv run sffm league        # verified live league facts
uv run sffm score-line --rec 8 --rec-yd 120 --rec-td 1
```
