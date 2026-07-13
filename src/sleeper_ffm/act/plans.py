"""Confirm-gated transaction plans for manual Sleeper execution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TransactionPlan:
    """A non-mutating execution plan for one recommendation."""

    action_id: str
    kind: str
    command: str
    status: str
    confirm_phrase: str
    steps: list[str]
    warnings: list[str]


def build_transaction_plan(action_id: str, kind: str, command: str) -> TransactionPlan:
    """Build a manual execution checklist without submitting anything to Sleeper."""
    normalized = kind.upper()
    confirm_phrase = f"CONFIRM {normalized} {action_id}"
    steps = [
        "Open Sleeper manually.",
        "Verify league, roster, asset names, and any FAAB or pick terms.",
        f"Execute only if the command still matches intent: {command}",
        "Record the result back in app findings after completion.",
    ]
    warnings = [
        "This app does not submit Sleeper transactions.",
        "Re-check injuries, depth charts, and breaking news before acting.",
    ]
    return TransactionPlan(
        action_id=action_id,
        kind=normalized,
        command=command,
        status="READY_FOR_MANUAL_CONFIRMATION",
        confirm_phrase=confirm_phrase,
        steps=steps,
        warnings=warnings,
    )
