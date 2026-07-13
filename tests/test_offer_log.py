"""Offer log — unit tests (file I/O only, no network calls)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch


def _with_path(tmp: Path):
    """Context: patch DATA_DIR so offer_log writes to tmp."""
    from sleeper_ffm.model import offer_log
    return patch.object(offer_log, "_OFFERS_PATH", tmp / "offers.jsonl")


def _sample_offer(partner_id: int = 2, give_label: str = "WR-A", receive_label: str = "RB-B") -> dict:
    return {
        "partner_roster_id": partner_id,
        "give": [{"label": give_label, "asset_id": "g1", "kind": "player", "position": "WR", "value": 80.0}],
        "receive": [{"label": receive_label, "asset_id": "r1", "kind": "player", "position": "RB", "value": 90.0}],
        "acceptance_score": 70,
        "confidence": "HIGH",
        "priority": 75,
        "give_value": 80.0,
        "receive_value": 90.0,
        "value_delta": 10.0,
        "target_need": "RB",
        "partner_need": "WR",
        "rationale": "test",
        "command": "test cmd",
        "evidence_count": 5,
        "calibration": "OWNER-HISTORY",
        "calibration_notes": "ok",
        "partner_name": "Partner",
    }


def test_append_writes_new_offers(tmp_path):
    from sleeper_ffm.model import offer_log

    with _with_path(tmp_path):
        offer_log.append_offers([_sample_offer()], logged_at="2026-07-12T00:00:00+00:00")
        offers = offer_log.list_offers()

    assert len(offers) == 1
    assert offers[0]["sent"] is False
    assert "offer_id" in offers[0]
    assert offers[0]["logged_at"] == "2026-07-12T00:00:00+00:00"


def test_append_is_idempotent(tmp_path):
    from sleeper_ffm.model import offer_log

    with _with_path(tmp_path):
        offer_log.append_offers([_sample_offer()], logged_at="t1")
        offer_log.append_offers([_sample_offer()], logged_at="t2")
        offers = offer_log.list_offers()

    assert len(offers) == 1  # same offer_id, not duplicated


def test_mark_sent(tmp_path):
    from sleeper_ffm.model import offer_log

    with _with_path(tmp_path):
        offer_log.append_offers([_sample_offer()], logged_at="t1")
        all_offers = offer_log.list_offers()
        oid = all_offers[0]["offer_id"]

        result = offer_log.mark_sent(oid)
        assert result is True

        updated = offer_log.list_offers()
        assert updated[0]["sent"] is True


def test_mark_sent_unknown_id(tmp_path):
    from sleeper_ffm.model import offer_log

    with _with_path(tmp_path):
        offer_log.append_offers([_sample_offer()], logged_at="t1")
        result = offer_log.mark_sent("nonexistent")
    assert result is False


def test_list_offers_filter_sent(tmp_path):
    from sleeper_ffm.model import offer_log

    offer_a = _sample_offer(partner_id=2, give_label="A-give", receive_label="A-recv")
    offer_b = _sample_offer(partner_id=3, give_label="B-give", receive_label="B-recv")

    with _with_path(tmp_path):
        offer_log.append_offers([offer_a, offer_b], logged_at="t1")
        all_offers = offer_log.list_offers()
        offer_log.mark_sent(all_offers[0]["offer_id"])

        pending = offer_log.list_offers(sent=False)
        sent = offer_log.list_offers(sent=True)

    assert len(pending) == 1
    assert len(sent) == 1


def test_list_offers_empty_when_no_file(tmp_path):
    from sleeper_ffm.model import offer_log

    with _with_path(tmp_path):
        offers = offer_log.list_offers()
    assert offers == []
