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
        "trade_plan": {
            "posture": "BUY",
            "plan": "Consolidate for a title window.",
            "trade_recs": [],
            "sequencing": "A before B",
        },
        "market_edge": {
            "buys": [{"player": "Underpriced RB", "thesis": "TD-regression buy-low"}],
            "sells": [],
            "reconciliations": "No board conflicts this week.",
        },
        "waiver_plan": {
            "waiver_recs": [
                {"player": "Backup RB", "faab_bid": 12, "drop": "Deep stash", "tier": "PRIORITY"}
            ],
            "holds": ["Trendy but capped WR"],
        },
        "owner_dossiers": [
            {
                "target": "roster 3 (Rival B)",
                "exploit_plan": "Squeeze their RB surplus.",
                "angles": [],
                "watch_items": ["their 2027 1st"],
            }
        ],
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
        "trade_plan": 1,
        "market_edge": 1,
        "waiver_plan": 1,
        "owner_dossier": 1,
    }
    assert resp.json()["total"] == 10

    trades = client.get("/findings/", params={"kind": "trade"}).json()
    assert len(trades) == 2
    assert all(t["body"]["generated_at"] == "2026-07-13T00:00:00+00:00" for t in trades)


def test_consolidated_sections_fan_out_to_their_kinds(client: TestClient) -> None:
    """The folded-in analyses store under the same kinds their old /ai/* surfaces used."""
    client.post("/findings/bulk", json=_valid_doc())
    edge = client.get("/findings/", params={"kind": "market_edge"}).json()
    assert len(edge) == 1 and edge[0]["body"]["buys"][0]["player"] == "Underpriced RB"
    plan = client.get("/findings/", params={"kind": "trade_plan"}).json()
    assert plan[0]["body"]["posture"] == "BUY"
    dossiers = client.get("/findings/", params={"kind": "owner_dossier"}).json()
    assert dossiers[0]["body"]["target"] == "roster 3 (Rival B)"


def test_a_new_run_replaces_the_standing_but_history_persists(client: TestClient) -> None:
    """Two bulk runs → standing shows only the latest; both persist on disk for grading."""
    import time

    run1 = _valid_doc()
    run1["narrative"] = "Run one column."
    client.post("/findings/bulk", json=run1)
    time.sleep(0.005)
    run2 = _valid_doc()
    run2["narrative"] = "Run two column."
    client.post("/findings/bulk", json=run2)

    standing = client.get("/findings/standing").json()
    narratives = [f["body"]["narrative"] for f in standing if f["kind"] == "narrative"]
    assert narratives == ["Run two column."]  # replaced, not appended
    run_ids = {f["run_id"] for f in standing if f["run_id"]}
    assert len(run_ids) == 1  # standing is exactly one run

    # Full history is still on the raw list (both runs), so grading past calls survives.
    all_narr = client.get("/findings/", params={"kind": "narrative"}).json()
    assert len(all_narr) == 2


def test_standalone_finding_persists_across_runs_in_the_standing(client: TestClient) -> None:
    """A standalone kind the master run doesn't produce (prospect_scout) survives a new run."""
    client.post("/findings/typed", json={"kind": "prospect_scout", "body": {"name": "Rook"}})
    client.post("/findings/bulk", json=_valid_doc())
    standing = client.get("/findings/standing").json()
    assert any(f["kind"] == "prospect_scout" for f in standing)


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


def test_dollar_prefixed_faab_bid_returns_422(client: TestClient) -> None:
    """A currency-formatted faab_bid ("$16") is a real, observed model output bug."""
    bad = _valid_doc()
    bad["waiver_recs"] = [{"player": "Backup RB", "faab_bid": "$16", "drop": "Deep stash"}]
    resp = client.post("/findings/bulk", json=bad)
    assert resp.status_code == 422
    assert client.get("/findings/").json() == []


def test_multi_asset_trade_leg_as_list_is_accepted(client: TestClient) -> None:
    """A 2-asset trade leg formatted as a JSON list is legitimate, not malformed."""
    doc = _valid_doc()
    doc["trade_recs"] = [
        {
            "partner": "Rival A",
            "send": ["2027 1st", "Young WR"],
            "receive": "Vet RB",
            "urgency": "MED",
        }
    ]
    resp = client.post("/findings/bulk", json=doc)
    assert resp.status_code == 201
    trades = client.get("/findings/", params={"kind": "trade"}).json()
    assert trades[0]["body"]["send"] == ["2027 1st", "Young WR"]
