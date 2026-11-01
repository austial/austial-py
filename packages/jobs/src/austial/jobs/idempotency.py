"""Jobs-scoped idempotency store.

Independent from ``austial.security``'s idempotency store: that one caches
HTTP responses for retry replay; this one deduplicates ``JobQueue.enqueue``
calls that share an ``idempotency_key``, returning the id of the already-
enqueued job instead of creating a second one.
"""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable

from austial.common.decorators.injectable import Injectable


@runtime_checkable
class IdempotencyStore(Protocol):
    """Pluggable ``key -> job_id`` store.

    Implementations MUST make ``put_if_absent`` atomic: two concurrent callers
    with the same key must see one winner. The in-memory implementation uses a
    lock; a Redis-backed one would use ``SET NX``, a Postgres one an
    ``INSERT ... ON CONFLICT DO NOTHING``.
    """

    def get(self, key: str) -> str | None:
        """Return the previously stored job id for ``key``, or ``None``."""
        ...

    def put_if_absent(self, key: str, job_id: str) -> str:
        """Return the id that ended up bound to ``key``: ``job_id`` on a fresh
        write, or the existing value if one was already stored."""
        ...


@Injectable()
class InMemoryIdempotencyStore:
    """Reference implementation for tests and local dev. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._data.get(key)

    def put_if_absent(self, key: str, job_id: str) -> str:
        with self._lock:
            existing = self._data.get(key)
            if existing is not None:
                return existing
            self._data[key] = job_id
            return job_id

    def reset(self) -> None:
        """Clear all records. Useful in tests."""
        with self._lock:
            self._data.clear()
