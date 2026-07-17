---
name: engine-eval
description: >
  Run and iterate on the engine calibration + prompt fine-tuning eval harness.
  Use when Rob says "run the evals", "tune the trade engine", "check the
  calibration", "grade the last change", or after editing any model/season
  engine or the master briefing prompt. Runs deterministic scenario suites,
  grades tier-3 briefing/prompt output, diagnoses failures to a specific
  constant or file, and logs every iteration to the ledger.
---

# Engine Eval — calibration + prompt fine-tuning loop

## Purpose

Measure whether the deterministic engines (trade acceptance, dynasty
valuation, FAAB, waivers, start/sit, mispricing) and the master-briefing
prompt are producing correct, coherent output — then diagnose failures to a
specific constant or file, apply the minimal fix, re-run, and record whether
it helped. This is the "training loop" for the app's decision logic: scenario
suites are the train/holdout split, the ledger is the trajectory.

## Ground rules

- **Never** call `recommend_trade_offers(log_offers=True)` during an eval.
- **Never** let a tier-3 run reach `POST /findings/bulk` — grading is fully
  in-process via `grade_doc.py` (`MasterDocument.model_validate`), never the
  live server. No eval run should ever write to `data/findings.jsonl` or
  `data/offers.jsonl`.
- **Tune on `train` only.** Run `--split holdout` at most once per tuning
  change, and only after `train` has improved. A change justified solely by
  a holdout scenario is a violation of the split — revert it.
- **Always append the ledger** (`evals/runs/ledger.jsonl`), even for a run
  that finds nothing wrong (`change_kind: baseline`).

## Commands

```
uv run sffm eval run --tier 1 --split train                          # writes evals/runs/<run_id>.jsonl, appends ledger
uv run sffm eval run --tier 1 --split holdout                        # validation only — see ground rules
uv run sffm eval run --id trade.fleece_low_acceptance                # re-run one scenario during diagnosis
uv run sffm eval run --change-kind scenario --change-note "..."      # tag what kind of change this run follows
uv run sffm eval report                                              # pass-rate trajectory from the ledger
uv run sffm eval render-briefing trap_hallucinated_partner           # tier 3: print the rendered briefing
uv run sffm eval grade-doc trap_hallucinated_partner <doc.json>      # tier 3: scripted grade
```

## Reading results

Each scenario result has `scenario_id`, `engine`, `passed`, and a `checks`
list; each check carries `type`, `target`, `expected`, `actual`, `passed`,
`delta`. **Read the delta, not just the pass/fail** — a `compare` check that
fails by a hair is a different diagnosis than one that fails by 10x. An
`error` field (not a check failure) means the adapter itself crashed —
usually a scenario/engine signature mismatch, not a calibration problem; fix
the scenario or adapter, not the engine constant.

## Grading

**Tier 1 is fully scripted** — a scenario passes iff every check passes.
Nothing to judge.

**Tier 3 procedure:**
1. `render-briefing <fixture>` and save the output.
2. Spawn a `general-purpose` subagent whose prompt is the rendered briefing
   plus the reasoning/persona sections of the **actual**
   `.claude/skills/war-room-reason/SKILL.md` (read it fresh — never
   paraphrase from memory, since the production prompt chain is the thing
   under test). It must return only the MasterDocument JSON as text.
3. Run this **3 independent times** per fixture — LLM output is stochastic;
   one run is noise. Save each JSON.
4. `grade-doc <fixture> <doc.json>` for each of the 3; report the per-check
   pass rate (3/3 = pass, 2/3 = flaky, <=1/3 = fail).
5. Apply `evals/rubrics/tier3_rubric.md` to the prose-quality dimensions on
   at least one of the 3 docs; record both the scripted taxonomy codes and
   the rubric scores.
6. **Independent dynasty-strategy critique — required whenever a fixture
   plants a math-vs-strategy tension, in ANY decision type** (`trade_recs`,
   `waiver_recs`, `lineup_recs`, not just trades). Grounding checks and schema
   validity do NOT catch a mathematically clean recommendation that is bad
   dynasty strategy — a rebuilding team trading a future asset for short-term
   production at a positive value margin (`trap_timeline_mismatched_trade`),
   chasing the higher raw waiver-priority score into an already-deep position
   while ignoring an actual roster hole (`trap_waiver_roster_need_mismatch`),
   or starting the higher-season-average player while ignoring a stated
   game-script/blowout risk (`trap_startsit_game_script_risk`). For each
   draft, spawn a SEPARATE fresh `general-purpose` subagent with NO memory of
   how the draft was produced. Give it only: the full rendered briefing (so
   it has the relevant context — contention/title-equity for trades, full
   roster composition for waivers, the stated game-script signal for
   lineups) and the draft's relevant array only (`trade_recs`, `waiver_recs`,
   or `lineup_recs` — not the narrative, so the critic judges the
   recommendation on its own merits, not the drafting agent's framing). Ask
   it explicitly: "Does this recommendation make sound dynasty fantasy
   football sense given this team's own stated context — independent of
   whether the raw score/margin/average favors it? Verdict: SOUND /
   QUESTIONABLE / UNSOUND, with reasoning." A response that never reconciles
   the recommendation against the planted tension is itself a finding,
   whether the critic calls the recommendation sound or not — record that
   separately from the critic's verdict on the recommendation itself.

Failure taxonomy: `HALLUCINATED_ENTITY`, `STALE_NUMBER`, `SCHEMA_VIOLATION`,
`UNJUSTIFIED_CONFIDENCE`, `MISSED_PLANTED_SIGNAL`, `VAGUE_REC`,
`TIMELINE_MISMATCH` (a trade recommendation that never reconciles against the
team's own stated contention window/timeline), and `FIXTURE_STALE` (a
`must_mention`/`allowed_player_names` check broke because of an *intentional*
prompt-wording edit — report distinctly, don't count it as a model failure;
update the fixture in `briefings.py` instead).

## Scenario-bug gate

Before changing any engine constant, argue both hypotheses out loud: "the
engine is wrong" vs. "the scenario's expected bound is wrong." Scenario
expectations encode fantasy judgment (e.g. "a fair swap should score 54-85")
and can themselves be miscalibrated. A scenario edit is a legitimate fix —
but it must be logged with `change_kind: scenario`, never bundled with an
engine-constant change in the same run. If you can't tell which is wrong,
say so in the ledger note rather than guessing.

## Diagnosis map

| Failure signature | Fix location |
|---|---|
| Acceptance bucket wrong at large margins | `src/sleeper_ffm/model/trade_acceptance.py` `_acceptance_score` (line ~353): base 42, margin coeff 0.35 (line ~370), clamps ±22/24 |
| Fit-driven acceptance errors | `trade_acceptance.py` `_score_position_fit` (~181) |
| Sweetener/window insensitivity | `trade_acceptance.py` `_window_bonus` (~339), `_pick_sweetener` (~255) |
| Age monotonicity / curve shape | `src/sleeper_ffm/model/dynasty.py` `_PEAK_AGE`, `_DECAY_RATE`, `_ASCENT_RATE`, `_DISCOUNT_RATE`, `_PROJECTION_HORIZON` |
| Taxi discount ratio wrong | `dynasty.py` `value_player` (~line 210, the `*= 0.80`) |
| Pick value ordering/level | `dynasty.py` `_PICK_ROUND_BASE`; live branch: `src/sleeper_ffm/market/blend.py` `market_pick_value` |
| FAAB over/under-bid | `src/sleeper_ffm/model/faab_market.py` `predicted_clearing_price` percentile mapping, `recommended_bid`; fallback tiers in `src/sleeper_ffm/season/waivers.py` `_faab_estimate`/`_bid_range` |
| Waiver priority ordering | `waivers.py` `_POSITION_BUMP`, trend weight, youth bonus |
| Lineup solver suboptimal | `src/sleeper_ffm/season/startsit.py` `_solve_lineup` |
| Mispricing verdict wrong side | `src/sleeper_ffm/model/mispricing.py` `_verdict` threshold |
| Market-calibration rank_corr too low | `dynasty.py` age-curve constants, or `src/sleeper_ffm/market/blend.py` blend weights |
| Tier-3 hallucination / missed ack | `src/sleeper_ffm/prompts/master.py` `build_master_briefing` wording; `.claude/skills/war-room-reason/SKILL.md` guards |
| Tier-3 SCHEMA_VIOLATION | doc shape vs `src/sleeper_ffm/api/routers/findings.py` `MasterDocument`; usually a war-room-reason output-format instruction |

## Iteration protocol

Every `eval run` invocation appends its own ledger entry automatically — there
is no separate logging step. Use `--change-kind`/`--change-note` on the run
that actually follows your edit so the ledger reads as a trajectory.

1. `uv run sffm eval run --tier 1 --split train` (baseline for this session
   if none yet: `--change-kind baseline`).
2. Group failures by taxonomy/engine; pick the highest-count category.
3. Run the scenario-bug gate.
4. Locate the responsible constant via the diagnosis map.
5. Make the **minimal** change; state the predicted effect before re-running.
6. `uv run sffm eval run --id <scenario_id> --change-kind <engine|scenario|prompt> --change-note "<what changed and why>"` to check the targeted fix.
7. `uv run sffm eval run --tier 1 --split train --change-kind <same> --change-note "full re-run after <scenario_id> fix"` (a fix to one scenario can regress another sharing the same constant).
8. If train improved: `uv run sffm eval run --tier 1 --split holdout --change-kind <same> --change-note "..."` once.
9. Conventional commit (`fix(model): ...` or `feat(eval): ...`) if the user
   asks for the change to be committed.

## Stop conditions

Stop when train pass-rate is 100% and holdout is at or above its previous
level, **or** after 3 iterations with no improvement — report the plateau and
stop rather than thrashing on constants that aren't the actual bottleneck.
