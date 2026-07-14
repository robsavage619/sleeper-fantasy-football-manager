"""Admin refresh + status endpoint tests (all fetches monkeypatched — no network)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import sleeper_ffm.api.routers.admin as admin
from sleeper_ffm.api.app import create_app


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """TestClient with a reset job state."""
    monkeypatch.setattr(
        admin,
        "_JOB",
        {"status": "idle", "started_at": None, "finished_at": None, "sources": {}},
        raising=True,
    )
    return TestClient(create_app())


def test_status_shape(client: TestClient) -> None:
    body = client.get("/admin/refresh/status").json()
    assert set(body) == {"job", "freshness"}
    assert body["job"]["status"] == "idle"
    assert set(body["freshness"]) == {
        "sleeper_players",
        "nflverse_weekly",
        "nflverse_snaps",
        "fantasycalc",
    }
    for source in body["freshness"].values():
        assert "exists" in source and "mtime" in source
    assert "cached_seasons" in body["freshness"]["nflverse_weekly"]


def test_refresh_runs_sources_and_clears_cache(client: TestClient, monkeypatch) -> None:
    cleared: list[bool] = []
    monkeypatch.setattr(admin, "_refresh_sleeper", lambda: {"players": 1})
    monkeypatch.setattr(admin, "_refresh_nflverse", lambda: {"weekly_rows": 2})
    monkeypatch.setattr(admin, "_refresh_fantasycalc", lambda date: {"entries": 3})
    monkeypatch.setattr(admin, "_clear_caches", lambda: cleared.append(True))

    resp = client.post("/admin/refresh")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

    # TestClient runs background tasks synchronously before returning the response.
    status = client.get("/admin/refresh/status").json()["job"]
    assert status["status"] == "done"
    assert cleared == [True]
    assert {k: v["ok"] for k, v in status["sources"].items()} == {
        "sleeper": True,
        "nflverse": True,
        "fantasycalc": True,
        "cache_clear": True,
    }


def test_one_source_failure_is_isolated_and_reported(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(admin, "_refresh_sleeper", lambda: {"players": 1})
    monkeypatch.setattr(
        admin, "_refresh_nflverse", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    monkeypatch.setattr(admin, "_refresh_fantasycalc", lambda date: {"entries": 3})
    monkeypatch.setattr(admin, "_clear_caches", lambda: None)

    client.post("/admin/refresh")
    job = client.get("/admin/refresh/status").json()["job"]
    sources = job["sources"]
    assert job["status"] == "error"  # one source failed — surfaced, not swallowed
    assert sources["sleeper"]["ok"] is True
    assert sources["nflverse"]["ok"] is False
    assert "boom" in sources["nflverse"]["error"]
    assert sources["fantasycalc"]["ok"] is True
    assert sources["cache_clear"]["ok"] is True


def test_concurrent_refresh_rejected_with_409(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        admin,
        "_JOB",
        {"status": "running", "started_at": "t", "finished_at": None, "sources": {}},
        raising=True,
    )
    resp = client.post("/admin/refresh")
    assert resp.status_code == 409
