"""Bounded retry helper — retries transient failures, propagates the rest."""

from __future__ import annotations

import pytest

from sleeper_ffm.net import retry_call


def test_retries_then_succeeds() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("blip")
        return "ok"

    assert retry_call(flaky, attempts=3, base_delay=0.1, sleep=slept.append) == "ok"
    assert calls["n"] == 3
    assert slept == [0.1, 0.2]  # exponential backoff between the two retries


def test_exhausts_and_reraises_last() -> None:
    def always() -> str:
        raise TimeoutError("down")

    with pytest.raises(TimeoutError, match="down"):
        retry_call(always, attempts=3, base_delay=0.0, sleep=lambda _s: None)


def test_non_retryable_exception_propagates_immediately() -> None:
    calls = {"n": 0}

    def bad() -> str:
        calls["n"] += 1
        raise ValueError("permanent")

    with pytest.raises(ValueError, match="permanent"):
        retry_call(bad, attempts=3, exceptions=(TimeoutError,), sleep=lambda _s: None)
    assert calls["n"] == 1  # never retried
