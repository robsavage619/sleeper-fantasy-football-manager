"""Append-only trade offer log.

Every time ``recommend_trade_offers()`` runs, we log all offers to
``data/offers.jsonl`` so there's a persistent record of what was generated,
what was sent, and what the outcome was.

Each line is a JSON object with:
  - All fields from ``TradeOfferRecommendation`` (as a dict)
  - ``offer_id``: deterministic hash of (partner_roster_id, give_labels, receive_label)
  - ``logged_at``: ISO-8601 timestamp (injected by caller, not this module)
  - ``sent``: bool — toggled via ``mark_sent()`` when the user acts on the offer
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from sleeper_ffm.config import DATA_DIR

log = logging.getLogger(__name__)

_OFFERS_PATH = DATA_DIR / "offers.jsonl"


def _offer_id(offer_dict: dict) -> str:
    """Derive a stable offer ID from partner + assets.  Not a UUID — deterministic."""
    give_labels = sorted(a["label"] for a in offer_dict.get("give", []))
    receive_labels = sorted(a["label"] for a in offer_dict.get("receive", []))
    key = f"{offer_dict.get('partner_roster_id')}|{give_labels}|{receive_labels}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def append_offers(offers: list[dict], logged_at: str) -> None:
    """Append a batch of offers to the log file (idempotent by offer_id).

    Existing entries with the same offer_id are NOT duplicated — we only write
    offers not yet in the log. Call this from ``recommend_trade_offers()``.

    Args:
        offers: List of offer dicts (dataclasses.asdict output).
        logged_at: ISO-8601 timestamp string (passed by caller to avoid time deps).
    """
    _OFFERS_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load existing IDs to skip duplicates.
    existing_ids: set[str] = set()
    if _OFFERS_PATH.exists():
        for line in _OFFERS_PATH.read_text().splitlines():
            try:
                existing_ids.add(json.loads(line)["offer_id"])
            except (json.JSONDecodeError, KeyError):
                pass

    new_rows = 0
    with _OFFERS_PATH.open("a") as fh:
        for offer in offers:
            oid = _offer_id(offer)
            if oid in existing_ids:
                continue
            row = {**offer, "offer_id": oid, "logged_at": logged_at, "sent": False}
            fh.write(json.dumps(row) + "\n")
            new_rows += 1

    log.info("offer_log: appended %d new offers (%d already existed)", new_rows, len(existing_ids))


def mark_sent(offer_id: str) -> bool:
    """Toggle ``sent=True`` on an existing offer log entry.

    Rewrites the file in place (the log stays small — typically <500 entries).

    Args:
        offer_id: The offer_id to update.

    Returns:
        True if the offer was found and updated, False if not found.
    """
    if not _OFFERS_PATH.exists():
        return False

    lines = _OFFERS_PATH.read_text().splitlines()
    updated = False
    new_lines = []
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            new_lines.append(line)
            continue
        if entry.get("offer_id") == offer_id:
            entry["sent"] = True
            updated = True
        new_lines.append(json.dumps(entry))

    if updated:
        _OFFERS_PATH.write_text("\n".join(new_lines) + "\n")
    return updated


def list_offers(sent: bool | None = None) -> list[dict]:
    """Return all logged offers, optionally filtered by sent status.

    Args:
        sent: If True, return only sent offers. If False, return only unsent.
            If None (default), return all.

    Returns:
        List of offer dicts, most-recently-logged first.
    """
    if not _OFFERS_PATH.exists():
        return []

    rows: list[dict] = []
    for line in _OFFERS_PATH.read_text().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if sent is None or entry.get("sent") == sent:
            rows.append(entry)

    rows.reverse()  # most recent first
    return rows
