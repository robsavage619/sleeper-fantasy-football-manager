"""Tier-1 eval runner — executes scenarios, grades checks, writes results + ledger."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sleeper_ffm.config import REPO_ROOT
from sleeper_ffm.evals.runners import ADAPTERS
from sleeper_ffm.evals.scenarios import RUNS_DIR, Scenario, evaluate_check, load_scenarios

log = logging.getLogger(__name__)


@dataclass
class ScenarioResult:
    """Pass/fail outcome for one scenario, with every check's actual value."""

    scenario_id: str
    engine: str
    passed: bool
    checks: list[dict[str, Any]]
    error: str | None = None


def _git_sha() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        )
        return proc.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_scenario(scenario: Scenario) -> ScenarioResult:
    """Run one scenario's adapter and grade every check against its output."""
    adapter = ADAPTERS.get(scenario.engine)
    if adapter is None:
        return ScenarioResult(
            scenario.id,
            scenario.engine,
            False,
            [],
            error=f"no adapter for engine '{scenario.engine}'",
        )
    try:
        case_results = adapter(scenario)
        check_results = [evaluate_check(check, case_results) for check in scenario.checks]
    except Exception as exc:
        log.warning("scenario %s errored: %s", scenario.id, exc)
        return ScenarioResult(scenario.id, scenario.engine, False, [], error=str(exc))

    return ScenarioResult(
        scenario_id=scenario.id,
        engine=scenario.engine,
        passed=all(c.passed for c in check_results),
        checks=[asdict(c) for c in check_results],
    )


def run_suite(
    split: str = "train",
    tier: int | None = 1,
    scenario_id: str | None = None,
    change_kind: str = "engine",
    change_note: str = "",
) -> dict[str, Any]:
    """Run a split's scenarios, write graded results, and append a ledger entry.

    Args:
        split: ``"train"`` or ``"holdout"``.
        tier: Restrict to scenarios of this tier, or None for all.
        scenario_id: Restrict to a single scenario id (diagnosis re-runs).
        change_kind: ``"engine" | "scenario" | "prompt" | "baseline"`` for the ledger.
        change_note: Free-text ledger note describing what changed since the last run.

    Returns:
        A dict with ``run_id``, ``run_path``, ``results`` (list of ScenarioResult),
        and the ledger entry fields.
    """
    scenarios = load_scenarios(split)
    if tier is not None:
        scenarios = [s for s in scenarios if s.tier == tier]
    if scenario_id is not None:
        scenarios = [s for s in scenarios if s.id == scenario_id]

    results = [run_scenario(s) for s in scenarios]
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    run_path = RUNS_DIR / f"{run_id}.jsonl"
    with run_path.open("w") as f:
        for r in results:
            f.write(json.dumps({"run_id": run_id, **asdict(r)}) + "\n")

    ledger_entry = {
        "run_id": run_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "split": split,
        "tier": tier,
        "scenarios_run": len(results),
        "passed": passed,
        "failed": failed,
        "flaky": 0,
        "change_kind": change_kind,
        "change_note": change_note,
        "files_touched": [],
    }
    with (RUNS_DIR / "ledger.jsonl").open("a") as f:
        f.write(json.dumps(ledger_entry) + "\n")

    return {"run_id": run_id, "run_path": str(run_path), "results": results, **ledger_entry}
