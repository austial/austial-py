"""``RateLimitStore`` protocol + ``InMemoryRateLimitStore`` reference impl.

The store is the pluggable backend for ``RateLimitGuard``. A production system
supplies a Redis-backed implementation; the in-memory default keeps tests and
single-process deployments honest.

The store's contract is a fixed-window counter: given a ``key`` and a ``period``
in seconds, ``hit`` returns ``(count, reset_at_epoch)`` for the current window,
incrementing the count as a side effect. Windows are aligned to wall-clock
seconds so a fleet of workers converges on the same buckets.
"""

from __future__ import annotations

import threading
import time
from typing import Protocol, runtime_checkable

from austial.common.decorators.injectable import Injectable


@runtime_checkable
class RateLimitStore(Protocol):
    """Pluggable backend for the ``RateLimitGuard``.

    Implementations must be safe to call from multiple asyncio tasks (and,
    for a shared backend, from multiple workers)."""

    def hit(self, key: str, period_seconds: int) -> tuple[int, int]:
        """Increment the counter for ``key`` inside its current window and
        return ``(count, reset_at_epoch)``."""
        ...


@Injectable()
class InMemoryRateLimitStore:
    """Thread-safe, process-local fixed-window counter.

    Not shared across workers -- swap for a Redis-backed store in a
    multi-process deployment. Windows are aligned to wall-clock seconds
    (``epoch // period``)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> (window_start_epoch, count)
        self._counters: dict[str, tuple[int, int]] = {}

    def hit(self, key: str, period_seconds: int) -> tuple[int, int]:
        now = int(time.time())
        window_start = (now // period_seconds) * period_seconds
        reset_at = window_start + period_seconds
        with self._lock:
            existing = self._counters.get(key)
            if existing is None or existing[0] != window_start:
                self._counters[key] = (window_start, 1)
                return 1, reset_at
            count = existing[1] + 1
            self._counters[key] = (window_start, count)
            return count, reset_at

    def reset(self) -> None:
        """Clear all counters. Useful in tests."""
        with self._lock:
            self._counters.clear()
