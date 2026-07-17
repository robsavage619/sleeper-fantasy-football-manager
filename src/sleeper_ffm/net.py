"""Shared network resilience helpers — bounded retry with exponential backoff.

Every outbound fetch in this codebase (Sleeper, nflverse, FantasyCalc, DynastyProcess)
is a single unguarded call: one transient 429/timeout and the caller degrades or throws.
:func:`retry_call` wraps a fetch in a small, capped retry so a blip self-heals without
turning into a stale-cache fallback or a degraded briefing section.

Kept deliberately tiny — no jitter, no circuit breaker. ``sleep`` is injectable so tests
never wait on real time.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

log = logging.getLogger(__name__)

# Default transient failures worth a retry. Callers pass their own tuple when the client
# raises library-specific errors (e.g. httpx.HTTPStatusError).
DEFAULT_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (OSError, TimeoutError)


def retry_call[T](
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    exceptions: tuple[type[BaseException], ...] = DEFAULT_RETRY_EXCEPTIONS,
    label: str = "request",
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn``, retrying on ``exceptions`` with exponential backoff.

    Args:
        fn: Zero-arg callable performing the fetch.
        attempts: Total tries (>= 1). The last failure is re-raised.
        base_delay: Seconds before the first retry; doubles each subsequent retry.
        exceptions: Exception types that trigger a retry. Anything else propagates immediately.
        label: Short name used in retry log lines.
        sleep: Sleep function (injectable for tests).

    Returns:
        Whatever ``fn`` returns on the first successful call.

    Raises:
        The last caught exception if every attempt fails (or any non-retryable exception).
    """
    last: BaseException | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return fn()
        except exceptions as exc:
            last = exc
            if attempt >= attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            log.warning(
                "%s: attempt %d/%d failed (%s); retrying in %.1fs",
                label,
                attempt,
                attempts,
                exc,
                delay,
            )
            sleep(delay)
    assert last is not None  # loop only exits via return or a caught exception
    raise last
