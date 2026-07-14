from __future__ import annotations

from sleeper_ffm.schedule import scheduler


def test_disabled_under_pytest() -> None:
    # pytest sets PYTEST_CURRENT_TEST, so the app never starts a live scheduler
    # during the test suite.
    assert scheduler._disabled() is True
    assert scheduler.scheduler_info() == {"enabled": False, "jobs": []}


def test_env_flag_disables(monkeypatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("SFFM_SCHEDULER", "0")
    assert scheduler._disabled() is True


def test_registers_all_jobs_when_enabled(monkeypatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("SFFM_SCHEDULER", "1")
    scheduler._scheduler = None
    sched = scheduler.start_scheduler()
    try:
        assert sched is not None
        info = scheduler.scheduler_info()
        assert info["enabled"] is True
        ids = {job["id"] for job in info["jobs"]}
        assert {"status_daily", "status_sunday", "status_gameday", "full_weekly"} <= ids
        # Every job has a computed next-fire time.
        assert all(job["next_run"] for job in info["jobs"])
    finally:
        scheduler.stop_scheduler()
    assert scheduler.scheduler_info()["enabled"] is False
