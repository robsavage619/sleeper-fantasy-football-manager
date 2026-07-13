"""Owners router — behavioral profiles + graded league report card."""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, HTTPException

from sleeper_ffm.model.owner_profile import build_owner_profiles

log = logging.getLogger(__name__)

router = APIRouter(prefix="/owners", tags=["owners"])


@router.get("/profiles")
def get_owner_profiles() -> list[dict]:
    """Return a behavioral profile for every owner in the league."""
    return [dataclasses.asdict(p) for p in build_owner_profiles()]


@router.get("/report-card")
def get_report_card() -> list[dict]:
    """Return the ranked, graded league report card for every manager."""
    from sleeper_ffm.model.report_card import build_report_card

    try:
        return build_report_card()
    except Exception as exc:
        log.exception("build_report_card failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/transaction-value")
def get_transaction_value() -> list[dict]:
    """Return fantasy points added via waivers and trades (latest completed season)."""
    from sleeper_ffm.model.transaction_value import build_transaction_value

    try:
        return build_transaction_value()
    except Exception as exc:
        log.exception("build_transaction_value failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/draft-profile")
def get_draft_profile() -> list[dict]:
    """Return per-manager draft tendencies + best picks across league history."""
    from sleeper_ffm.model.draft_profile import build_draft_profiles

    try:
        return build_draft_profiles()
    except Exception as exc:
        log.exception("build_draft_profiles failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
