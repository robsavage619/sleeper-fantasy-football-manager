# sleeper-fantasy-football-manager

AI dynasty fantasy football GM for Sleeper. Scoring-aware valuation, a dynasty asset model
(players + keepers + 3 years of picks in one currency), owner behavioral profiling, and
**Claude Code as the reasoning engine** (deterministic engines build prompts → Claude Code
reasons → findings post back → dashboard renders). No runtime LLM key in the backend.

League: *The League* — 2026 dynasty, full PPR with bonuses, 10 teams, 1QB / no K / no DST.
Writes to Sleeper drive the real web UI (no stored credentials) and are always confirm-gated;
waiver moves require explicit approval.

## Layout

- `src/sleeper_ffm/scoring/` — the scoring engine (linchpin): stat line → fantasy points.
- `src/sleeper_ffm/sleeper/` — read-only Sleeper API client (+ dynasty history walk).
- `src/sleeper_ffm/nflverse/` — historical stats ingestion (`nfl-data-py` → parquet).
- `src/sleeper_ffm/model/` — valuation, trends, projections, dynasty assets, pick market, owner profiles.
- `src/sleeper_ffm/prompts/`, `reasoning/` — prompt-builders + the findings store Claude Code writes to.
- `src/sleeper_ffm/act/`, `schedule/` — Playwright write layer (confirm-gated) + local scheduler.
- `frontend/` — React/Vite/Tailwind dashboard.

## Dev

```sh
uv sync
uv run pytest
uv run sffm league        # verified live league facts
uv run sffm score-line --rec 8 --rec-yd 120 --rec-td 1
```
