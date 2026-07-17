"""Eval harness self-checks: scenario files parse and the runner executes.

Deliberately does NOT assert scenario pass/fail — the harness's job is
surfacing calibration drift for a human/agent to diagnose, not gating CI on
scenarios that may legitimately be mid-tuning.
"""

from __future__ import annotations

from sleeper_ffm.evals.harness import run_scenario, run_suite
from sleeper_ffm.evals.runners import ADAPTERS
from sleeper_ffm.evals.scenarios import load_scenarios


def test_train_scenarios_parse() -> None:
    scenarios = load_scenarios("train")
    assert scenarios
    for scenario in scenarios:
        assert scenario.engine in ADAPTERS, (
            f"{scenario.id} references unknown engine '{scenario.engine}'"
        )
        assert scenario.checks


def test_holdout_scenarios_parse() -> None:
    scenarios = load_scenarios("holdout")
    assert scenarios
    for scenario in scenarios:
        assert scenario.engine in ADAPTERS, (
            f"{scenario.id} references unknown engine '{scenario.engine}'"
        )


def test_train_holdout_ids_disjoint() -> None:
    train_ids = {s.id for s in load_scenarios("train")}
    holdout_ids = {s.id for s in load_scenarios("holdout")}
    assert not (train_ids & holdout_ids)


def test_every_scenario_runs_without_crashing() -> None:
    """Adapter mechanics work end-to-end (a scenario may still fail its checks)."""
    for scenario in load_scenarios("train") + load_scenarios("holdout"):
        result = run_scenario(scenario)
        assert result.error is None, f"{scenario.id} adapter crashed: {result.error}"


def test_run_suite_writes_results_and_ledger(tmp_path, monkeypatch) -> None:
    import sleeper_ffm.evals.harness as harness_mod
    import sleeper_ffm.evals.scenarios as scenarios_mod

    monkeypatch.setattr(scenarios_mod, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(harness_mod, "RUNS_DIR", tmp_path)

    result = run_suite(split="train", tier=1, change_kind="baseline", change_note="test")

    assert (tmp_path / f"{result['run_id']}.jsonl").exists()
    ledger_path = tmp_path / "ledger.jsonl"
    assert ledger_path.exists()
    assert result["scenarios_run"] == result["passed"] + result["failed"]
