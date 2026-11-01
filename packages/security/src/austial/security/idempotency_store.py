"""``IdempotencyStore`` protocol + ``InMemoryIdempotencyStore`` reference impl.

An idempotency record captures the response produced for a mutation so the
guard can replay it verbatim if the client retries with the same
``Idempotency-Key``. Records expire after ``ttl_seconds``; a replay with a
different request body while the record is still alive is a conflict.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from austial.common.decorators.injectable import Injectable


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """Snapshot of a response bound to an ``Idempotency-Key``."""

    key: str
    request_hash: str
    status_code: int
    body: Any
    stored_at: float


@runtime_checkable
class IdempotencyStore(Protocol):
    """Pluggable backend for ``IdempotencyKeyGuard``."""

    def get(self, key: str) -> IdempotencyRecord | None:
        """Return the record for ``key`` if it is still within TTL, else ``None``."""
        ...

    def put(self, record: IdempotencyRecord) -> None:
        """Persist a record (overwriting any earlier record for the same key)."""
        ...


@Injectable()
class InMemoryIdempotencyStore:
    """Thread-safe, process-local record cache with lazy TTL expiry."""

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._records: dict[str, IdempotencyRecord] = {}

    def get(self, key: str) -> IdempotencyRecord | None:
        now = time.time()
        with self._lock:
            record = self._records.get(key)
            if record is None:
                return None
            if now - record.stored_at > self._ttl:
                self._records.pop(key, None)
                return None
            return record

    def put(self, record: IdempotencyRecord) -> None:
        with self._lock:
            self._records[record.key] = record

    def reset(self) -> None:
        """Clear all records. Useful in tests."""
        with self._lock:
            self._records.clear()
