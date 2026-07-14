"""Findings store — the shared state between Claude Code reasoning and the dashboard.

Architecture (mirrors SHC lab_findings.py):
    Claude Code reads a prompt → reasons → calls ``post_finding`` (via CLI or
    JSON write) → FastAPI serves ``/findings`` → React dashboard renders.

Findings are stored in-memory (current session) and also persisted to
``data/findings.jsonl`` for the dashboard to query. The FastAPI router in
``api/routers/findings.py`` wraps this store.

Usage from CLI / Claude Code:
    ``sffm finding post --type draft --body '{"recommendation": "take CJ Stroud"}'``
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
    prompt_hash: str | None = None  # sha256 of the input prompt (for dedup)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict."""
        return asdict(self)


def post_finding(kind: str, body: dict[str, Any], prompt_hash: str | None = None) -> Finding:
    """Append a new finding to the store and persist it to disk.

    Args:
        kind: Decision type (``"draft"``, ``"waiver"``, ``"trade"``, etc.).
        body: Structured reasoning output from Claude Code.
        prompt_hash: Optional SHA-256 of the prompt for dedup detection.

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
