<p align="center">
  <img src="banner.svg" alt="Sleeper War Room — AI dynasty fantasy football GM" width="100%"/>
</p>

<p align="center">
  <b>An AI general manager for a dynasty fantasy football league that answers one question:</b><br/>
  <i>"What is this player, pick, or trade worth to <b>my</b> team, under <b>my</b> league's exact scoring, <b>right now</b>?"</i>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12-blue.svg" alt="python 3.12"/></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/api-FastAPI-009688" alt="FastAPI"/></a>
  <a href="https://pola.rs/"><img src="https://img.shields.io/badge/data-Polars-cd792c" alt="Polars"/></a>
  <a href="frontend/"><img src="https://img.shields.io/badge/frontend-React%2019-61dafb" alt="React 19"/></a>
  <a href="frontend/"><img src="https://img.shields.io/badge/build-Vite%208-646cff" alt="Vite 8"/></a>
  <a href="tests/"><img src="https://img.shields.io/badge/tests-210%20passing-success" alt="210 tests"/></a>
  <a href=".claude/skills/war-room-reason/SKILL.md"><img src="https://img.shields.io/badge/reasoning-Claude%20Code-8a63d2" alt="Claude Code"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-source--available-lightgrey" alt="license"/></a>
</p>

---

## The 60-second pitch

Every dynasty trade tool prices a player with a single number — a market value that's identical whether the deal helps a rebuilding team or a title favorite, and whether your league scores standard PPR or something else entirely. **That number is wrong twice over.** It ignores *who's asking* and it ignores *how your league actually scores.*

**Sleeper War Room** is a full-stack AI GM built around the one thing off-the-shelf tools can't see: **your commissioner's exact scoring settings.** Every valuation, projection, and matchup call is re-derived under this league's real rules — full PPR *with yardage and threshold bonuses*, 1QB, no K, no DST — not the generic PPR the national market prices on. When those two disagree, that gap is a tradeable edge that only you can compute.

On top of that scoring core sits a dynasty asset model (players, keepers, and three years of picks in one currency), a Monte-Carlo season simulator that turns roster strength into **championship probability**, owner behavioral profiling learned from the league's real trade history, and — the reasoning layer — **Claude Code as the GM**, reading the entire franchise state and posting back one grounded strategic brief. There is **no runtime LLM key in the backend**: deterministic engines build the prompt, Claude reasons, findings post back, the dashboard renders.

It is read-only by design — it recommends, explains, ranks, and logs decisions, but never submits a Sleeper transaction. The recommendations are the product.

> **For evaluators:** the screenshots below are live application output. Start with [The War Room](#the-war-room) for the product, [The edge](#the-edge--league-exact-scoring) for the thesis, and [AI engineering](#ai-engineering--claude-code-as-the-reasoning-engine) for the technical spine. Every surface is backed by a deterministic engine with tests.

---

## The War Room

> *The command center. Read your situation, see the next best moves, act on the brief.*

<p align="center">
  <img src="docs/screenshots/war-room.png" alt="War Room — league state, action queue, and AI intel findings" width="100%"/>
</p>

The War Room opens on the franchise at a glance — league format, traded-pick inventory, FAAB — then an **action queue** of the highest-leverage moves, each an engine-built, value-balanced trade or waiver with a FIT score and an urgency. Below it, the **intel feed**: the findings Claude Code has reasoned and posted back, in the war-room analyst's voice — including, above, a multi-paragraph read on this league's *actual* draft-order convention (reverse of prior-season final standings) that corrected an earlier bug and recomputed the real projected slot. That is the reasoning engine showing its work, grounded in verified league facts.

---

## Market Edges

> *The trade brain. Title equity, who's buying and selling, and where the market is wrong — for us specifically.*

<p align="center">
  <img src="docs/screenshots/market-edges.png" alt="Market Edges — title equity, contention windows, scoring-leverage mispricing, and TD regression" width="100%"/>
</p>

Four engines on one page:

- **Title equity** — a Monte-Carlo season simulation ([`season_sim.py`](src/sleeper_ffm/model/season_sim.py)) ranks every roster by championship probability, so "contend vs. rebuild" is a number, not a vibe.
- **Contention windows** — each rival classified `WIN-NOW` / `SUSTAIN` / `RETOOL` / `REBUILD` from odds + core age + youth share, with *what they want* and *what they should move* — target your trades at the fit.
- **League-specific mispricing** — the flagship. Each player re-scored under our rules *and* under generic PPR; the gap, normalized against his position, is the edge the national market can't see. In the live board above, the BUY column skews to **QBs and workhorse backs** — exactly the profiles our passing and yardage bonuses reward more than standard PPR does (Joe Flacco +11.3%, Derrick Henry +11.1%, James Cook +10.1%).
- **Regression watch** — touchdowns-over-expected flags sell-highs (Davante Adams rode +9.1 TDs over his yardage) and buy-lows (Bijan Robinson, −5.1) before the market corrects.

---

## Matchup Lab

> *The lineup brain. Win probability, weather and stadium history, playoff schedule, and the wire.*

<p align="center">
  <img src="docs/screenshots/matchup-lab.png" alt="Matchup Lab — win probability, stadium/weather splits, playoff strength of schedule, wire watch, handcuffs" width="100%"/>
</p>

Pre-lock **win probability** for the week's matchup (margin modeled as normal over both teams' projected scores), each rostered player's **historical splits by venue and conditions** (dome vs. exposed, cold, wind, per-stadium — Derrick Henry is +6.1 FP/game indoors), an opponent-adjusted **playoff strength-of-schedule** weighted to fantasy weeks 15–17, a **wire early-warning** feed of snap-share risers still on the market, and a **handcuff/leverage map** of exposed backups and stashes that sit behind rivals' stars.

---

## GM Profiles & the rest of the app

> *Know your league. The trade engine only works if you know who's on the other side.*

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/gm-profiles.png" alt="GM Profiles — owner behavioral profiling" width="100%"/></td>
    <td width="50%"><img src="docs/screenshots/trades.png" alt="Trades — acceptance-model offers" width="100%"/></td>
  </tr>
</table>

Every owner is profiled from the league's **real transaction history** — an archetype (pick hoarder, win-now star collector, …), an approachability read, trade-partner tendencies, and positional needs — which feeds the acceptance model behind every proposed offer and the **negotiation copilot** that tailors a pitch to how *that* owner values assets. Eleven surfaces in all:

| Route | View |
|---|---|
| `/` | **War Room** — command center + AI intel findings |
| `/edges` | **Market Edges** — mispricing, title equity, contention, regression |
| `/matchups` | **Matchup Lab** — win probability, weather, SoS, wire, handcuffs |
| `/draft` | **Draft Board** — live board, value-based recs, standings-projected slot |
| `/roster` | **Roster** — dynasty values, age curve, lineup |
| `/trades` | **Trades** — acceptance-model offers with two-sided value accounting |
| `/waivers` | **Waivers** — claim cards, bid ranges, drop candidates, downside |
| `/owners` | **GM Profiles** — owner behavioral profiling |
| `/report-card` | **Report Card** — historical manager grades across seasons |
| `/prospects` | **Prospects** — rookie scouting (CFBD college + combine + market) |
| `/narrative` | **War Room Brief** — the single-prompt GM update |

---

## The edge — league-exact scoring

The moat is one file: [`scoring/engine.py`](src/sleeper_ffm/scoring/engine.py). It turns a stat line into fantasy points under the league's real `scoring_settings` — never hardcoded weights, so it stays correct if the commissioner changes a rule — and it derives the threshold bonuses (100/200-yard, 300/400 pass-yard, 25-completion, 20-carry) the national market ignores.

Because every valuation flows through it, the app can do something no off-the-shelf tool can: **re-score the same season twice** — once under our rules, once under canonical PPR — and rank the players whose value diverges. That's [`model/mispricing.py`](src/sleeper_ffm/model/mispricing.py), and the design detail that makes it honest is the position-median normalization: a uniform league-wide difference (say 6-pt vs. 4-pt passing TDs) cancels out, so what survives is the *player-specific* profile edge, not the scoring level. The result is a buy/sell board denominated in the same dynasty units as everything else.

Everything downstream inherits the same discipline — the [dynasty asset model](src/sleeper_ffm/model/dynasty.py) (age-curve-projected FPAR, players and picks in one currency), the [market blend](src/sleeper_ffm/market/blend.py) (market-anchored 65/35, because the market is cross-positionally sane and the model contributes a within-position ranking), and the [in-house sabermetrics](src/sleeper_ffm/model/sabermetrics.py) (consistency, TD dependence, usage quality, xFP), all computed under this league's exact scoring.

---

## AI engineering — Claude Code as the reasoning engine

> *One discipline: deterministic engines build the prompt, the model reasons, findings post back, and the model is never the source of a fact.*

The architecture deliberately keeps the LLM out of the backend. Instead:

1. **Deterministic engines build a structured briefing.** [`prompts/master.py`](src/sleeper_ffm/prompts/master.py) composes league state, roster, title equity, contention windows, mispricing, regression, handcuffs, wire, weather, and playoff SoS into **one prompt** — pure and testable (`build_master_briefing` takes a context and a timestamp; no clock, no network).
2. **Claude Code reasons over the whole franchise.** The [`war-room-reason`](.claude/skills/war-room-reason/SKILL.md) skill fetches the briefing, reasons in a veteran-analyst voice, then — critically — **drafts, independently critiques, fixes, and only then posts.** A single unverified pass has produced real errors (invented trade partners, stale numbers restated as current); the critique step exists to catch that class of mistake before it reaches the dashboard.
3. **Findings post back as structured JSON.** The [findings store](src/sleeper_ffm/reasoning/findings.py) is the boundary; the dashboard renders what's posted. Facts not literally in the briefing (a partner name, a pick-class percentage) must be fetched fresh from the API and cited — never asserted from memory.

The same pattern powers the [negotiation copilot](src/sleeper_ffm/prompts/negotiation.py) and the [GM's weekly address](src/sleeper_ffm/prompts/gm_address.py). It's the runnable version of the retrieve-before-generate, structured-output, self-critiquing-agent patterns this kind of work demands in production — with grounding enforced at the file boundary rather than trusted to the model.

---

## The data layer

Everything is sourced from public APIs and cached to local parquet; nothing here is a secret, and the heavy caches are gitignored.

| Source | Coverage | Role |
|---|---|---|
| **Sleeper API** | live league | rosters, matchups, transactions, trending, drafts, traded picks |
| **nflverse** weekly | 2014–2025 | per-player box scores — the scoring engine's primary input |
| **nflverse** snaps | 2014–2025 | opportunity trend + wire early-warning |
| **nflverse** schedules | + roof / temp / wind | defense-vs-position, strength of schedule, stadium & weather splits |
| **nflverse** depth charts | latest snapshot | handcuff / leverage map |
| **nflverse** injuries | current season | real-world intel feed |
| **FantasyCalc / DynastyProcess** | live | dynasty market anchor (player + pick values) |
| **CFBD** + combine | college | rookie prospect scouting |

The scoring engine ingests two weekly formats (the archived `player_stats` era ≤2023 and the current `stats_player` era 2024+) and reconciles them on load — including a `diagonal_relaxed` concat so multi-season reads span the schema boundary cleanly.

---

## Under the hood

**Backend** — Python 3.12, FastAPI, Polars, `uv`, `ruff`, `pyright`. ~18K lines across **32 model engines** and **32 API routers**; **210 tests**, all pure-logic where it counts (the statistical cores are unit-tested without network). A `typer` CLI (`sffm <verb>`) drives ingestion, scoring, and the war-room loop.

**Frontend** — React 19, TypeScript 6, Vite 8, Tailwind 4, TanStack Query, Zustand, Framer Motion. A single-page dashboard with 11 routes, wired to the live backend.

```
src/sleeper_ffm/
├── scoring/     # league-exact stat-line → fantasy points (the linchpin)
├── sleeper/     # read-only Sleeper API client + dynasty history walk
├── nflverse/    # historical stats ingestion (nfl-data-py → parquet)
├── cfbd/ college/ combine   # college + combine data for rookie scouting
├── model/       # 32 engines: valuation, dynasty assets, mispricing, season sim,
│                #   contention, regression, stadium/weather, schedule strength,
│                #   handcuffs, wire watch, gameday, owner dossiers, sabermetrics…
├── market/      # FantasyCalc / DynastyProcess anchor + model↔market blend
├── prompts/     # deterministic prompt-builders (master briefing, negotiation, address)
├── reasoning/   # the findings store Claude Code writes back to
├── season/ draft/ act/ schedule/   # start-sit, waivers, draft assistant, plans, scheduler
└── api/         # FastAPI app + routers
frontend/        # React 19 / Vite 8 / Tailwind 4 dashboard (11 routes)
.claude/         # the war-room-reason skill + launch config — the agent loop
```

---

## Local setup

```bash
# Backend
uv sync
uv run pytest                 # 210 tests
uv run sffm ingest            # seed nflverse parquet (2014–2025) → data/nflverse/
uv run sffm serve             # FastAPI on http://127.0.0.1:8000

# Frontend (proxies /api → backend)
cd frontend && npm install
npm run dev                   # → http://localhost:5173
```

Quick CLI sanity checks — no server needed:

```bash
uv run sffm league                                       # verified live league facts
uv run sffm score-line --rec 8 --rec-yd 120 --rec-td 1   # a stat line under our rules
uv run sffm roster                                       # dynasty values for my roster
```

The AI loop: with the server up, run the `/war-room-reason` skill in Claude Code (it fetches `GET /ai/briefing`, reasons, and posts one verified findings document back), then open the dashboard.

---

## How to read this repo

This is a personal project — an end-to-end demonstration of scoring-aware valuation, simulation, and agentic product design, not a tool distributed for others to run. The screenshots and engines are the artifact.

- **10 min** — this README. The screenshots are live output; [The edge](#the-edge--league-exact-scoring) is the thesis in three paragraphs.
- **30 min** — read [`scoring/engine.py`](src/sleeper_ffm/scoring/engine.py) and [`model/mispricing.py`](src/sleeper_ffm/model/mispricing.py) (the moat), then [`prompts/master.py`](src/sleeper_ffm/prompts/master.py) and [`.claude/skills/war-room-reason/SKILL.md`](.claude/skills/war-room-reason/SKILL.md) (the agent loop).
- **An afternoon** — `uv sync && uv run sffm ingest && uv run sffm serve`, start the frontend, and open `/edges` and `/matchups`. Every board is backed by an engine with tests.

See [`CHANGELOG.md`](CHANGELOG.md) for the build history.

---

## License

This repository is **source-available** for evaluation, research, and education. Viewing and reading are permitted; copying, redistribution, commercial use, and ML-training on the source are not, without prior written permission. See [`LICENSE`](LICENSE). For commercial licensing or questions: **rob.savage@me.com**.

---

*Built end to end — data engineering, scoring-exact valuation, Monte-Carlo simulation, and an agentic reasoning loop — as a demonstration of how a real front office would use AI: to sharpen decisions, with the model grounded and its work checked, never as the source of a fact. This is the work, not a packaged tool.*
