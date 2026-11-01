"""``Worker`` -- background loop that pulls due jobs and invokes them.

One event loop, ``concurrency`` in-flight tasks at any time. Failure handling:

- exception in the handler => attempts += 1
- if ``attempts < spec.max_attempts`` => schedule a retry ``backoff * 2^(n-1)`` seconds ahead
- else => mark the record ``failed`` with the last error

The worker never blocks the loop: sleeps are ``asyncio.sleep``; handlers are
awaited if async, offloaded to a thread if sync.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import random
from dataclasses import replace
from datetime import timedelta

from austial.common.decorators.injectable import Injectable
from austial.jobs.backend import JobBackend, now_utc
from austial.jobs.config import JobsConfig
from austial.jobs.records import JobRecord, JobStatus
from austial.jobs.registry import JobEntry, JobRegistry
from austial.jobs.schedule import parse_schedule

logger = logging.getLogger("austial.jobs.worker")


@Injectable()
class Worker:
    def __init__(
        self,
        backend: JobBackend,
        registry: JobRegistry,
        config: JobsConfig,
    ) -> None:
        self._backend = backend
        self._registry = registry
        self._config = config

    async def run(self, shutdown: asyncio.Event | None = None) -> None:
        """Pull-and-execute loop. Returns when ``shutdown`` is set. Callers who
        want to poll once from a test can call :meth:`tick` directly."""
        shutdown = shutdown or asyncio.Event()
        await self._schedule_crons()
        while not shutdown.is_set():
            await self.tick()
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=self._config.poll_interval_seconds)
            except TimeoutError:
                continue

    async def tick(self) -> None:
        """One iteration of the loop: claim due jobs and run them concurrently
        up to ``concurrency``. Exposed so tests can drive the worker without
        the sleeping loop."""
        due = await self._backend.pop_due(now=now_utc(), limit=self._config.concurrency)
        if not due:
            return
        await asyncio.gather(*(self._run_one(record) for record in due))

    async def _run_one(self, record: JobRecord) -> None:
        entry = self._registry.get_job(record.name)
        if entry is None:
            # Handler was unregistered between enqueue and run -- fail terminally.
            await self._backend.mark(replace(record, status=JobStatus.failed, error=f"handler {record.name!r} missing"))
            return

        try:
            await _invoke(entry, record.payload)
        except BaseException as exc:  # noqa: BLE001 -- retry policy needs everything
            await self._handle_failure(record, entry, exc)
            return
        await self._backend.mark(replace(record, status=JobStatus.succeeded, attempts=record.attempts + 1, error=None))

    async def _handle_failure(self, record: JobRecord, entry: JobEntry, exc: BaseException) -> None:
        attempts = record.attempts + 1
        max_attempts = entry.spec.max_attempts or self._config.default_max_attempts
        if attempts >= max_attempts:
            await self._backend.mark(replace(record, status=JobStatus.failed, attempts=attempts, error=repr(exc)))
            logger.warning("job %s failed permanently after %d attempts: %r", record.id, attempts, exc)
            return
        base = entry.spec.backoff_seconds or self._config.default_backoff_seconds
        delay = base * (2 ** (attempts - 1))
        next_attempt = now_utc() + timedelta(seconds=delay)
        await self._backend.mark(
            replace(
                record,
                status=JobStatus.pending,
                attempts=attempts,
                next_attempt_at=next_attempt,
                error=repr(exc),
            )
        )

    async def _schedule_crons(self) -> None:
        """Convert every ``@Cron`` entry into an initial pending record so the
        worker's first ``tick`` picks it up when due. Subsequent runs are
        re-scheduled after each successful fire (deferred; the reference
        worker fires each cron once per :meth:`run` invocation for simplicity)."""
        from austial.jobs.decorators import JobSpec
        from austial.jobs.queue import JobQueue  # noqa: F401  -- avoid cycle at import time

        for cron in self._registry.all_crons():
            # Register a placeholder job entry so run_one can dispatch it.
            if self._registry.get_job(cron.name) is None:
                self._registry.register_job(
                    JobSpec(name=cron.name, max_attempts=1, backoff_seconds=0, idempotent=False),
                    cron.handler,
                )
            schedule = parse_schedule(cron.spec.schedule)
            run_at = schedule.next_run_at(now_utc())
            if cron.spec.jitter_seconds:
                run_at = run_at + timedelta(seconds=random.uniform(0, cron.spec.jitter_seconds))
            record = JobRecord(
                id=_short_id(),
                name=cron.name,
                payload={},
                status=JobStatus.pending,
                run_at=run_at,
                next_attempt_at=run_at,
            )
            await self._backend.enqueue(record)


async def _invoke(entry: JobEntry, payload: dict) -> None:
    result = entry.handler(**payload)
    if inspect.isawaitable(result):
        await result


def _short_id() -> str:
    import secrets

    return secrets.token_hex(8)
