"""Findings store — the shared state between Claude Code reasoning and the dashboard.

Architecture (mirrors SHC lab_findings.py):
    Claude Code reads a prompt → reasons → calls ``post_finding`` (via CLI or
    JSON write) → FastAPI serves ``/findings`` → React dashboard renders.

Findings are stored in-memory (current session) and also persisted to
``data/findings.jsonl`` for the dashboard to query. The FastAPI router in
``api/routers/findings.py`` wraps this store.

Usage from CLI / Claude Code:
    ``sffm finding draft --body '{"recommendation": "take CJ Stroud"}'``
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from sleeper_ffm.config import DATA_DIR

log = logging.getLogger(__name__)

_FINDINGS_FILE = DATA_DIR / "findings.jsonl"

# In-memory store (one process; re-hydrated from file on startup)
_store: list[Finding] = []
_seq: int = 0


@dataclass
class Finding:
    """A single reasoning output from Claude Code, keyed by decision type."""

    finding_id: str
    kind: str  # "draft" | "waiver" | "trade" | "startsit" | "owner_dossier" | "pick_arb"
    body: dict[str, Any]
    created_at: float = field(default_factory=time.time)
    # Master-run batch id. All findings from one /findings/bulk share it, so the live
    # "standing" is exactly the newest run (a new run replaces the old). None for
    # standalone posts (e.g. the prospect_scout drill-down).
    run_id: str | None = None
    prompt_hash: str | None = None  # sha256 of the input prompt (for dedup)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict."""
        return asdict(self)


def post_finding(
    kind: str,
    body: dict[str, Any],
    prompt_hash: str | None = None,
    run_id: str | None = None,
) -> Finding:
    """Append a new finding to the store and persist it to disk.

    Args:
        kind: Decision type (``"draft"``, ``"waiver"``, ``"trade"``, etc.).
        body: Structured reasoning output from Claude Code.
        prompt_hash: Optional SHA-256 of the prompt for dedup detection.
        run_id: Master-run batch id; shared by every finding from one bulk post.

    Returns:
        The saved ``Finding``.
    """
    global _seq
    _seq += 1
    # Sequence suffix guarantees uniqueness when several findings of the same kind
    # are posted in the same millisecond (e.g. the /findings/bulk fan-out).
    finding_id = f"{kind}_{int(time.time() * 1000)}_{_seq}"
    finding = Finding(
        finding_id=finding_id,
        kind=kind,
        body=body,
        prompt_hash=prompt_hash,
        run_id=run_id,
    )
    _store.append(finding)
    _persist(finding)
    log.info("finding posted: %s", finding_id)
    return finding


def list_findings(kind: str | None = None, limit: int = 50) -> list[Finding]:
    """Return recent findings, optionally filtered by kind.

    Args:
        kind: If set, return only findings of this type.
        limit: Maximum number of findings to return (most recent first).

    Returns:
        Findings sorted newest-first.
    """
    items = _store if kind is None else [f for f in _store if f.kind == kind]
    return sorted(items, key=lambda f: f.created_at, reverse=True)[:limit]


def latest_finding(kind: str) -> Finding | None:
    """Return the most recent finding of the given kind.

    Args:
        kind: Decision type to filter on.

    Returns:
        The newest matching finding, or ``None`` if none exists.
    """
    items = [f for f in _store if f.kind == kind]
    return max(items, key=lambda f: f.created_at) if items else None


def standing_findings() -> list[Finding]:
    """The current standing: the latest master run's findings + standalone kinds.

    "Persistent until the new run replaces it" — the newest master run (identified by the
    most recent ``run_id``) fully replaces the prior run's kinds. Findings with no run_id
    (standalone posts like the per-prospect ``prospect_scout`` drill-down, which is
    deliberately not part of the single run) survive as newest-per-kind, so they persist
    across runs rather than vanishing.

    Returns:
        The standing findings, newest-first.
    """
    run_ids = [f.run_id for f in _store if f.run_id is not None]
    latest_run = max(run_ids, key=_run_seq, default=None)
    run_findings = [f for f in _store if f.run_id == latest_run] if latest_run else []
    run_kinds = {f.kind for f in run_findings}

    # All standalone (no run_id) findings of kinds the master run does not produce — every
    # one, not newest-per-kind: multi-item kinds like prospect_scout need the full set, and
    # the caller (buildStanding) does its own per-kind grouping/windowing. Legacy findings
    # from before run tagging (all run_id=None) fall entirely into this bucket, so a
    # pre-migration store degrades to plain newest-per-kind — unchanged behavior.
    standalone = [f for f in _store if f.run_id is None and f.kind not in run_kinds]

    return sorted([*run_findings, *standalone], key=lambda f: f.created_at, reverse=True)


def _run_seq(run_id: str) -> int:
    """Sortable millisecond stamp from a ``run_<ms>`` id; 0 if unparseable."""
    try:
        return int(run_id.split("_", 1)[1])
    except (IndexError, ValueError):
        return 0


def load_findings_from_disk() -> None:
    """Re-hydrate the in-memory store from the persisted JSONL file.

    Called once at server startup. Idempotent — safe to call multiple times.
    """
    global _store
    if not _FINDINGS_FILE.exists():
        return
    loaded: list[Finding] = []
    for line in _FINDINGS_FILE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            loaded.append(Finding(**d))
        except (json.JSONDecodeError, TypeError) as exc:
            log.warning("findings: skipping malformed line: %s", exc)
    _store = loaded
    log.info("findings: loaded %d findings from disk", len(_store))


def _persist(finding: Finding) -> None:
    _FINDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _FINDINGS_FILE.open("a") as fh:
        fh.write(json.dumps(finding.to_dict()) + "\n")
