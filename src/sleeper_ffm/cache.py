"""In-process TTL memoization for expensive, shared, read-only computations.

Used to collapse per-request recomputation (valuation scoring, league-history
HTTP walks) that would otherwise run once per partner in the O(N^2) trade and
war-room endpoints. Caches are process-local and cleared by ``clear_all()``
(called by the admin refresh flow after new data lands).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Hashable
from functools import wraps
from typing import Any, TypeVar

log = logging.getLogger(__name__)

_DEFAULT_TTL: float = 600.0  # 10 minutes

F = TypeVar("F", bound=Callable[..., Any])

# Registry of every cache dict so clear_all() can flush them on data refresh.
_REGISTRY: list[dict[Any, tuple[float, Any]]] = []
_LOCK = threading.Lock()


def ttl_cache(
    ttl: float = _DEFAULT_TTL,
    key: Callable[..., Hashable] | None = None,
) -> Callable[[F], F]:
    """Memoize a function's result for ``ttl`` seconds.

    Args:
        ttl: Seconds a cached entry stays fresh.
        key: Optional function mapping call args to a hashable cache key. Defaults
            to ``(args, sorted kwargs)``; supply this when an argument is unhashable
            (e.g. a Sleeper player dump) or irrelevant to the result.

    Returns:
        A decorator that adds TTL memoization and a ``.cache_clear()`` attribute.
    """

    def decorator(func: F) -> F:
        store: dict[Any, tuple[float, Any]] = {}
        with _LOCK:
            _REGISTRY.append(store)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = key(*args, **kwargs) if key else (args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            hit = store.get(cache_key)
            if hit is not None and now - hit[0] < ttl:
                return hit[1]
            result = func(*args, **kwargs)
            store[cache_key] = (now, result)
            return result

        wrapper.cache_clear = store.clear  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def clear_all() -> None:
    """Flush every TTL cache (call after new data lands)."""
    with _LOCK:
        for store in _REGISTRY:
            store.clear()
    log.info("cache: cleared %d in-process TTL caches", len(_REGISTRY))
