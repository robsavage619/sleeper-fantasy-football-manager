"""POST /findings/bulk — fan-out and validation tests (no network calls)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import sleeper_ffm.reasoning.findings as findings_store
from sleeper_ffm.api.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    """TestClient with an isolated in-memory findings store and temp persistence file."""
    monkeypatch.setattr(findings_store, "_store", [], raising=True)
    monkeypatch.setattr(findings_store, "_FINDINGS_FILE", tmp_path / "findings.jsonl", raising=True)
    return TestClient(create_app())


def _valid_doc() -> dict[str, Any]:
    return {
        "narrative": "The franchise is rebuilding around youth.",
        "trade_recs": [
            {"partner": "Rival A", "send": "RB1", "receive": "2027 1st", "urgency": "MED"},
            {"partner": "Rival B", "send": "WR3", "receive": "WR1", "urgency": "HIGH"},
        ],
        "waiver_recs": [{"player": "Backup RB", "faab_bid": 12, "drop": "Deep stash"}],
        "draft_recs": [],
        "prospect_notes": [
            {"name": "Rookie WR", "verdict": "STARTER", "rationale": "elite target share"}
        ],
        "lineup_recs": [{"start": "WR2", "sit": "WR4", "rationale": "matchup"}],
        "generated_at": "2026-07-13T00:00:00+00:00",
        "data_quality_ack": "Snap counts stale by one week.",
    }


def test_valid_document_stores_per_kind(client: TestClient) -> None:
    resp = client.post("/findings/bulk", json=_valid_doc())
    assert resp.status_code == 201
    stored = resp.json()["stored"]
    assert stored == {
        "narrative": 1,
        "trade": 2,
        "waiver": 1,
        "draft": 0,
        "prospect": 1,
        "lineup": 1,
    }
    assert resp.json()["total"] == 6

    trades = client.get("/findings/", params={"kind": "trade"}).json()
    assert len(trades) == 2
    assert all(t["body"]["generated_at"] == "2026-07-13T00:00:00+00:00" for t in trades)


def test_malformed_document_returns_422_and_stores_nothing(client: TestClient) -> None:
    bad = _valid_doc()
    del bad["waiver_recs"]  # missing required section
    resp = client.post("/findings/bulk", json=bad)
    assert resp.status_code == 422
    assert client.get("/findings/").json() == []


def test_wrong_type_section_returns_422(client: TestClient) -> None:
    bad = _valid_doc()
    bad["trade_recs"] = "not a list"
    resp = client.post("/findings/bulk", json=bad)
    assert resp.status_code == 422
    assert client.get("/findings/").json() == []
