"""Eval scenario schema, loader, and check evaluators.

Scenarios are JSON fixtures under ``evals/scenarios/<split>/*.json``. Each
scenario names an engine adapter (see ``runners.py``), supplies per-case
inputs, and lists checks to run against the adapter's output. Checks are
plain dicts (not a strict dataclass) since their shape varies by type.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sleeper_ffm.config import REPO_ROOT

EVALS_ROOT = REPO_ROOT / "evals"
SCENARIOS_DIR = EVALS_ROOT / "scenarios"
RUNS_DIR = EVALS_ROOT / "runs"
RUBRICS_DIR = EVALS_ROOT / "rubrics"


@dataclass
class Scenario:
    """One eval scenario: an engine call plus the checks its output must pass."""

    id: str
    tier: int
    engine: str
    rationale: str
    inputs: dict[str, Any]
    checks: list[dict[str, Any]]
    source: Path


def load_scenarios(split: str) -> list[Scenario]:
    """Load every scenario from ``evals/scenarios/<split>/*.json``.

    Args:
        split: ``"train"`` or ``"holdout"``.

    Returns:
        All scenarios across every suite file in the split, in file order.

    Raises:
        FileNotFoundError: If the split directory doesn't exist.
    """
    split_dir = SCENARIOS_DIR / split
    if not split_dir.is_dir():
        raise FileNotFoundError(f"no scenario split directory: {split_dir}")

    scenarios: list[Scenario] = []
    for path in sorted(split_dir.glob("*.json")):
        data = json.loads(path.read_text())
        for raw in data["scenarios"]:
            scenarios.append(
                Scenario(
                    id=raw["id"],
                    tier=raw["tier"],
                    engine=raw["engine"],
                    rationale=raw.get("rationale", ""),
                    inputs=raw["inputs"],
                    checks=raw["checks"],
                    source=path,
                )
            )
    return scenarios


@dataclass
class CheckResult:
    """Outcome of one scenario check, with the actual value for diagnosis."""

    type: str
    target: str
    expected: Any
    actual: Any
    passed: bool
    delta: float | None = None


def _resolve(case_results: dict[str, dict[str, Any]], case: str, field: str) -> Any:
    return case_results[case][field]


def _resolve_dotted(case_results: dict[str, dict[str, Any]], dotted: str) -> Any:
    case, field = dotted.split(".", 1)
    return _resolve(case_results, case, field)


def _ranks(values: list[float]) -> list[float]:
    """Average ranks (1-based, ties split evenly) for a Spearman correlation."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    result = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            result[order[k]] = avg_rank
        i = j + 1
    return result


def _spearman(a: list[float], b: list[float]) -> float:
    """Spearman rank correlation between two equal-length lists (no scipy dep)."""
    n = len(a)
    if n < 2:
        return 0.0
    ra, rb = _ranks(a), _ranks(b)
    mean_a, mean_b = sum(ra) / n, sum(rb) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb, strict=True))
    var_a = sum((x - mean_a) ** 2 for x in ra)
    var_b = sum((y - mean_b) ** 2 for y in rb)
    if var_a == 0 or var_b == 0:
        return 0.0
    return cov / (var_a * var_b) ** 0.5


_COMPARE_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}


def evaluate_check(check: dict[str, Any], case_results: dict[str, dict[str, Any]]) -> CheckResult:
    """Evaluate one scenario check against adapter output.

    Supported types: ``exact``, ``approx``, ``range``, ``ordering``, ``compare``
    (cross-case, e.g. monotonicity), ``ratio`` (cross-case ratio, e.g. a fixed
    discount multiplier), ``rank_corr`` (Spearman between two list fields in
    the same case, e.g. market-calibration).

    Args:
        check: One check dict from a scenario's ``checks`` list.
        case_results: Adapter output, keyed by case name.

    Returns:
        A ``CheckResult`` with the actual value populated for diagnosis.

    Raises:
        ValueError: If ``check["type"]`` is not a supported check type.
    """
    kind = check["type"]

    if kind == "exact":
        actual = _resolve(case_results, check["case"], check["field"])
        expected = check["value"]
        return CheckResult(
            kind, f"{check['case']}.{check['field']}", expected, actual, actual == expected
        )

    if kind == "approx":
        actual = _resolve(case_results, check["case"], check["field"])
        expected = check["value"]
        tol = check.get("tol", 0.0)
        delta = abs(actual - expected)
        return CheckResult(
            kind, f"{check['case']}.{check['field']}", expected, actual, delta <= tol, delta
        )

    if kind == "range":
        actual = _resolve(case_results, check["case"], check["field"])
        lo, hi = check["min"], check["max"]
        return CheckResult(
            kind, f"{check['case']}.{check['field']}", (lo, hi), actual, lo <= actual <= hi
        )

    if kind == "ordering":
        actual = _resolve(case_results, check["case"], check["field"])
        direction = check.get("direction", "desc")
        expected_sorted = sorted(actual, reverse=(direction == "desc"))
        return CheckResult(
            kind, f"{check['case']}.{check['field']}", direction, actual, actual == expected_sorted
        )

    if kind == "compare":
        left = _resolve_dotted(case_results, check["left"])
        right = _resolve_dotted(case_results, check["right"])
        op = check["op"]
        passed = _COMPARE_OPS[op](left, right)
        delta = (
            left - right
            if isinstance(left, int | float) and isinstance(right, int | float)
            else None
        )
        return CheckResult(
            kind,
            f"{check['left']} {op} {check['right']}",
            None,
            {"left": left, "right": right},
            passed,
            delta,
        )

    if kind == "ratio":
        a = _resolve(case_results, check["case_a"], check["field"])
        b = _resolve(case_results, check["case_b"], check["field"])
        expected = check["expected"]
        tol = check.get("tol", 0.02)
        actual_ratio = a / b if b else float("inf")
        delta = abs(actual_ratio - expected)
        return CheckResult(
            kind,
            f"{check['case_a']}.{check['field']} / {check['case_b']}.{check['field']}",
            expected,
            round(actual_ratio, 4),
            delta <= tol,
            round(delta, 4),
        )

    if kind == "rank_corr":
        a = _resolve(case_results, check["case"], check["field_a"])
        b = _resolve(case_results, check["case"], check["field_b"])
        min_corr = check.get("min", 0.75)
        corr = round(_spearman(a, b), 3)
        return CheckResult(
            kind,
            f"{check['case']} rank_corr({check['field_a']},{check['field_b']})",
            min_corr,
            corr,
            corr >= min_corr,
            round(corr - min_corr, 3),
        )

    raise ValueError(f"unknown check type: {kind}")
