# Tier-3 prose-quality rubric

`grade_doc` (see `src/sleeper_ffm/evals/grade_doc.py`) scripts everything that
can be scripted: schema validity, planted-fact presence, closed-universe
player names, FAAB bounds, data-quality acknowledgment. What's left is prose
judgment — score each dimension 0-5 per fixture, using the anchors below.
Record both the scripted taxonomy codes and these scores in the ledger note.

## Grounding (does every claim trace to the briefing?)

- **5** — every number and name cited appears verbatim (or trivially
  paraphrased) in the rendered briefing text.
- **3** — one number is rounded or restated imprecisely, but no invented facts.
- **0** — any figure, name, or claim not present in the briefing or a source
  the model says it fetched fresh.

## Decisiveness (war-room-reason persona: opinionated, not hedged)

- **5** — every recommendation names a specific action ("offer X for Y"), not
  a menu of options; ties are broken with a stated reason.
- **3** — mostly decisive, one recommendation hedges without a stated reason.
- **0** — recommendations read as a list of possibilities with no call made.

## Earned confidence (no unjustified certainty)

- **5** — confidence is stated once, plainly, exactly where the data actually
  supports or fails to support the claim; `data_quality_ack` covers every
  degraded or stale section, no more and no less.
- **3** — confidence is broadly right but one section over- or under-states
  what the data supports.
- **0** — a stale or degraded section is presented as current fact, or the
  voice hedges everywhere regardless of actual data quality.

## Rationale quality (would a real GM find this useful?)

- **5** — rationale explains the roster-construction or market logic behind
  the call (scarcity, aging curve, contention window), not just a restated
  number.
- **3** — rationale is present but generic ("good value") without the
  underlying reasoning.
- **0** — no rationale, or rationale contradicts the cited numbers.

## Strategic soundness (does the raw math say yes but real dynasty strategy say no?)

The math can check out — a positive value margin, a decent FIT score, a real
partner — and the trade can still be the wrong move. This dimension is
independent of the other four: a response can score 5/5 on grounding and
decisiveness while recommending a strategically backwards trade, if it never
weighs the acceptance-model's math against the team's own stated context
(contention window, timeline, aging curve, positional scarcity, roster
construction). This is NOT scriptable — grade it via an independent critique
pass (see the engine-eval skill's Tier 3 procedure), not a keyword search.

- **5** — the response explicitly reconciles the trade against the team's
  timeline/contention signal and either (a) recommends it with a stated
  reason it still fits, or (b) flags the tension and downgrades/declines the
  engine's "realistic offer" framing rather than parroting it.
- **3** — the response mentions the relevant context (e.g. "we're rebuilding")
  somewhere but doesn't connect it to the trade decision — a missed synthesis,
  not a fabrication.
- **0** — the response never connects the trade to the team's own
  contention/timeline context at all, or actively cites that context to
  support the wrong conclusion (e.g. "since we're rebuilding, take this
  win-now trade").

Common failure mode to watch for: an engine-flagged "realistic offer" or
positive value margin gets treated as license to skip judgment — the response
defaults to "the model said take it" instead of applying the same
roster-construction reasoning it uses everywhere else in the document.

## Reading a run

A prompt-wording change should move these scores across N=3 runs, not one
lucky sample — treat a single high/low run as noise. If a fixture's
`must_mention`/`allowed_player_names` check starts failing right after an
intentional edit to `prompts/master.py` wording, report it as `FIXTURE_STALE`
in the ledger note and update the fixture, not the model's grade.
