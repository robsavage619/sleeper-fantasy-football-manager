"""FastAPI router — trade offer log."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from sleeper_ffm.model.offer_log import append_offers, list_offers, mark_sent

router = APIRouter(prefix="/offers", tags=["offers"])
log = logging.getLogger(__name__)


@router.get("")
def get_offers(sent: bool | None = None) -> list[dict]:
    """Return logged trade offers, optionally filtered by sent status.

    Args:
        sent: true = only sent offers; false = only pending; omit = all.
    """
    return list_offers(sent=sent)


@router.post("/log")
def log_offers(offers: list[dict]) -> dict:
    """Append offers to the calibration log — an explicit user action.

    The recommendation endpoints are read-only; offers land in the log only when
    the user chooses to pursue them (e.g. PLAN / MARK SENT in the UI).

    Args:
        offers: Offer dicts (``TradeOfferRecommendation`` shape from /trades/offers).

    Returns:
        ``{"logged": <count submitted>}``.
    """
    now = datetime.now(UTC).isoformat()
    append_offers(offers, logged_at=now)
    return {"logged": len(offers)}


@router.patch("/{offer_id}/sent")
def mark_offer_sent(offer_id: str) -> dict:
    """Mark a trade offer as sent.

    Args:
        offer_id: The 12-character offer_id from the log.
    """
    updated = mark_sent(offer_id)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Offer {offer_id!r} not found in log")
    return {"offer_id": offer_id, "sent": True}
