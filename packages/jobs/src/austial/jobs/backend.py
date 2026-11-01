"""``JobBackend`` protocol + ``InMemoryJobBackend`` reference implementation.

The queue speaks to the backend, not to a particular storage system. Redis /
Postgres / Arq / Dramatiq wiring is deferred; ship an in-memory queue that
the product can swap.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from austial.common.decorators.injectable import Injectable
from austial.jobs.records import JobRecord, JobStatus


def _new_id() -> str:
    return secrets.token_hex(8)


@runtime_checkable
class JobBackend(Protocol):
    """Queue-storage contract. Every method is ``async`` so a real backend can
    talk to Redis/Postgres over an event-loop-friendly driver."""

    async def enqueue(self, record: JobRecord) -> JobRecord:
        """Persist ``record`` in the ``pending`` state; return the stored copy."""
        ...

    async def pop_due(self, *, now: datetime, limit: int) -> list[JobRecord]:
        """Atomically claim up to ``limit`` pending records whose ``next_attempt_at``
        (or ``run_at`` when unset) has passed. Claimed records are moved to
        ``running`` and returned."""
        ...

    async def mark(self, record: JobRecord) -> JobRecord:
        """Persist the record's new state (``running`` -> ``succeeded`` /
        ``failed`` / re-``pending`` for retry)."""
        ...

    async def cancel(self, job_id: str) -> bool:
        """Transition a ``pending`` record to ``cancelled``; return ``True`` if
        the job existed and was pending, ``False`` otherwise."""
        ...

    async def get(self, job_id: str) -> JobRecord | None:
        """Return the current record for ``job_id`` or ``None``."""
        ...

    async def all(self) -> list[JobRecord]:
        """Return a snapshot of every known record (debugging / status APIs)."""
        ...


@Injectable()
class InMemoryJobBackend:
    """Process-local job store. Not durable, not shared between workers, not for
    production. Serves as the default so a fresh install runs out of the box and
    tests don't need external infrastructure."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._records: dict[str, JobRecord] = {}

    def new_id(self) -> str:
        """Convenience for the queue to mint an id without importing ``secrets``."""
        return _new_id()

    async def enqueue(self, record: JobRecord) -> JobRecord:
        async with self._lock:
            self._records[record.id] = record
            return record

    async def pop_due(self, *, now: datetime, limit: int) -> list[JobRecord]:
        due: list[JobRecord] = []
        async with self._lock:
            for job_id, record in list(self._records.items()):
                if record.status is not JobStatus.pending:
                    continue
                ready = record.next_attempt_at or record.run_at
                if ready is not None and ready > now:
                    continue
                claimed = _replace(record, status=JobStatus.running)
                self._records[job_id] = claimed
                due.append(claimed)
                if len(due) >= limit:
                    break
        return due

    async def mark(self, record: JobRecord) -> JobRecord:
        async with self._lock:
            self._records[record.id] = record
            return record

    async def cancel(self, job_id: str) -> bool:
        async with self._lock:
            record = self._records.get(job_id)
            if record is None or record.status is not JobStatus.pending:
                return False
            self._records[job_id] = _replace(record, status=JobStatus.cancelled)
            return True

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            return self._records.get(job_id)

    async def all(self) -> list[JobRecord]:
        async with self._lock:
            return list(self._records.values())


def _replace(record: JobRecord, **changes: Any) -> JobRecord:
    """Frozen-dataclass replacement without pulling ``dataclasses.replace``'s
    edge cases across module boundaries."""
    from dataclasses import replace

    return replace(record, **changes)


def now_utc() -> datetime:
    """UTC ``now`` -- centralised so tests can monkeypatch a single symbol."""
    return datetime.now(UTC)
