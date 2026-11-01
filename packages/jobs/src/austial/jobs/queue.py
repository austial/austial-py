"""``JobQueue`` -- the enqueue/cancel/status entry point injected into product code.

The queue is a thin coordinator over :class:`JobBackend`, :class:`JobRegistry`
and :class:`IdempotencyStore`; product services depend on it, not on the
backend directly, so swapping in Redis/Arq/Dramatiq later is a module wiring
change with no application-code churn.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from austial.common.decorators.injectable import Injectable
from austial.jobs.backend import InMemoryJobBackend, JobBackend, now_utc
from austial.jobs.errors import UnknownJobError
from austial.jobs.idempotency import IdempotencyStore
from austial.jobs.records import JobRecord, JobStatus
from austial.jobs.registry import JobRegistry


@Injectable()
class JobQueue:
    def __init__(
        self,
        backend: JobBackend,
        registry: JobRegistry,
        idempotency: IdempotencyStore,
    ) -> None:
        self._backend = backend
        self._registry = registry
        self._idempotency = idempotency

    async def enqueue(
        self,
        name: str,
        *,
        payload: dict[str, Any] | None = None,
        run_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        """Enqueue a job by name. Returns the (new or existing) job id.

        When ``idempotency_key`` is provided, a second call with the same key
        returns the id of the first call without enqueuing a duplicate. This
        assumes the handler is idempotent (the default for ``@Job``); a
        non-idempotent handler must opt out at the decorator."""
        entry = self._registry.get_job(name)
        if entry is None:
            raise UnknownJobError(name)

        if idempotency_key is not None:
            existing = self._idempotency.get(idempotency_key)
            if existing is not None:
                return existing

        job_id = _mint_id(self._backend)
        record = JobRecord(
            id=job_id,
            name=name,
            payload=dict(payload or {}),
            attempts=0,
            status=JobStatus.pending,
            run_at=run_at,
            next_attempt_at=run_at,
        )
        await self._backend.enqueue(record)

        if idempotency_key is not None:
            # Race-safe: if another call beat us, drop the record we just wrote
            # and return the winner's id.
            winner = self._idempotency.put_if_absent(idempotency_key, job_id)
            if winner != job_id:
                await self._backend.cancel(job_id)
                return winner
        return job_id

    async def cancel(self, job_id: str) -> bool:
        return await self._backend.cancel(job_id)

    async def status(self, job_id: str) -> JobStatus | None:
        record = await self._backend.get(job_id)
        return record.status if record is not None else None

    async def get(self, job_id: str) -> JobRecord | None:
        """Return the full record (payload, attempts, error) -- useful in tests
        and for status endpoints that need more than the status column."""
        return await self._backend.get(job_id)


def _mint_id(backend: JobBackend) -> str:
    """Prefer the backend's own id minter when it exposes one (the in-memory
    default does), else fall back to secrets."""
    minter = getattr(backend, "new_id", None)
    if callable(minter):
        return minter()
    import secrets

    return secrets.token_hex(8)


__all__ = ["JobQueue", "now_utc", "InMemoryJobBackend"]
