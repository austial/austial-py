"""``austial.jobs`` unit tests.

Exercises the load-bearing behaviours: decorator metadata, in-memory backend
enqueue/pop cycle, worker success + retry + terminal failure, idempotency-key
deduplication, cancel-a-pending-job, and schedule parsing for the two shapes
the docs promise (``@every 30s`` and standard 5-field cron).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from austial.common.decorators.injectable import Injectable
from austial.core.metadata import get_metadata
from austial.jobs import (
    CRON_METADATA,
    JOB_METADATA,
    Cron,
    CronSpec,
    InMemoryIdempotencyStore,
    InMemoryJobBackend,
    Job,
    JobQueue,
    JobRecord,
    JobRegistry,
    JobsConfig,
    JobSpec,
    JobStatus,
    Worker,
    parse_schedule,
)

# @Cron / @Job metadata -----------------------------------------------------


def test_cron_decorator_sets_metadata():
    @Cron("*/5 * * * *", name="poll-feed", jitter_seconds=10)
    async def handler():
        pass

    spec = get_metadata(CRON_METADATA, handler)
    assert isinstance(spec, CronSpec)
    assert spec.schedule == "*/5 * * * *"
    assert spec.name == "poll-feed"
    assert spec.jitter_seconds == 10


def test_job_decorator_sets_metadata():
    @Job("send-remittance", max_attempts=5, backoff_seconds=60)
    async def handler():
        pass

    spec = get_metadata(JOB_METADATA, handler)
    assert isinstance(spec, JobSpec)
    assert spec.name == "send-remittance"
    assert spec.max_attempts == 5
    assert spec.backoff_seconds == 60
    assert spec.idempotent is True


# Registry discovery --------------------------------------------------------


def test_registry_discovers_job_from_injectable():
    @Injectable()
    class Payments:
        @Job("send-remittance")
        async def send(self, *, remittance_id: str) -> str:  # noqa: ARG002
            return "ok"

    registry = JobRegistry()
    registry.discover(Payments())

    entry = registry.get_job("send-remittance")
    assert entry is not None
    assert entry.spec.name == "send-remittance"


# Backend -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_backend_enqueue_and_pop_due_cycle():
    backend = InMemoryJobBackend()
    now = datetime.now(UTC)
    past = now - timedelta(seconds=1)
    future_at = now + timedelta(hours=1)
    record = JobRecord(id="a", name="noop", payload={}, run_at=past, next_attempt_at=past)
    await backend.enqueue(record)

    future = JobRecord(id="b", name="noop", payload={}, run_at=future_at, next_attempt_at=future_at)
    await backend.enqueue(future)

    due = await backend.pop_due(now=now, limit=10)
    assert [r.id for r in due] == ["a"]
    assert due[0].status is JobStatus.running

    # Second pop is empty because 'a' is running and 'b' is still in the future.
    assert await backend.pop_due(now=now, limit=10) == []


# JobQueue: enqueue + idempotency ------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_returns_id_for_known_job():
    registry = JobRegistry()
    registry.register_job(JobSpec(name="ping"), lambda: None)
    backend = InMemoryJobBackend()
    queue = JobQueue(backend=backend, registry=registry, idempotency=InMemoryIdempotencyStore())

    job_id = await queue.enqueue("ping", payload={"x": 1})
    record = await backend.get(job_id)
    assert record is not None
    assert record.name == "ping"
    assert record.payload == {"x": 1}
    assert record.status is JobStatus.pending


@pytest.mark.asyncio
async def test_enqueue_with_same_idempotency_key_returns_existing_id():
    registry = JobRegistry()
    registry.register_job(JobSpec(name="ping"), lambda: None)
    queue = JobQueue(backend=InMemoryJobBackend(), registry=registry, idempotency=InMemoryIdempotencyStore())

    first = await queue.enqueue("ping", idempotency_key="k1")
    second = await queue.enqueue("ping", idempotency_key="k1")
    assert first == second


@pytest.mark.asyncio
async def test_cancel_transitions_pending_to_cancelled():
    registry = JobRegistry()
    registry.register_job(JobSpec(name="ping"), lambda: None)
    backend = InMemoryJobBackend()
    queue = JobQueue(backend=backend, registry=registry, idempotency=InMemoryIdempotencyStore())

    job_id = await queue.enqueue("ping")
    assert await queue.cancel(job_id) is True
    assert (await queue.status(job_id)) is JobStatus.cancelled
    # A second cancel is a no-op because the job is no longer pending.
    assert await queue.cancel(job_id) is False


# Worker: success + retry + terminal fail ----------------------------------


@pytest.mark.asyncio
async def test_worker_invokes_registered_job_and_records_success():
    calls: list[dict] = []

    async def handler(**payload):
        calls.append(payload)

    registry = JobRegistry()
    registry.register_job(JobSpec(name="ping"), handler)
    backend = InMemoryJobBackend()
    queue = JobQueue(backend=backend, registry=registry, idempotency=InMemoryIdempotencyStore())
    worker = Worker(backend=backend, registry=registry, config=JobsConfig(poll_interval_seconds=0.01))

    job_id = await queue.enqueue("ping", payload={"x": 42})
    await worker.tick()

    record = await backend.get(job_id)
    assert record is not None
    assert record.status is JobStatus.succeeded
    assert record.attempts == 1
    assert calls == [{"x": 42}]


@pytest.mark.asyncio
async def test_worker_retries_transient_failure_then_fails_terminally():
    attempts = {"n": 0}

    async def flaky(**_payload):
        attempts["n"] += 1
        raise RuntimeError("boom")

    registry = JobRegistry()
    registry.register_job(JobSpec(name="flaky", max_attempts=3, backoff_seconds=0), flaky)
    backend = InMemoryJobBackend()
    queue = JobQueue(backend=backend, registry=registry, idempotency=InMemoryIdempotencyStore())
    worker = Worker(backend=backend, registry=registry, config=JobsConfig(default_backoff_seconds=0))

    job_id = await queue.enqueue("flaky")
    # First tick: attempts=1, backoff=0*2^0=0 => stays pending, ready immediately.
    await worker.tick()
    record = await backend.get(job_id)
    assert record is not None
    assert record.status is JobStatus.pending

    # Two more ticks reach max_attempts.
    await worker.tick()
    await worker.tick()
    record = await backend.get(job_id)
    assert record is not None
    assert record.status is JobStatus.failed
    assert record.attempts == 3
    assert record.error is not None and "boom" in record.error
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_worker_run_stops_on_shutdown_event():
    registry = JobRegistry()
    backend = InMemoryJobBackend()
    worker = Worker(backend=backend, registry=registry, config=JobsConfig(poll_interval_seconds=0.01))
    shutdown = asyncio.Event()

    async def stopper():
        await asyncio.sleep(0.05)
        shutdown.set()

    await asyncio.gather(worker.run(shutdown=shutdown), stopper())


# Schedule parsing ---------------------------------------------------------


def test_every_shorthand_yields_next_run_after_exact_interval():
    schedule = parse_schedule("@every 30s")
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert schedule.next_run_at(now) == now + timedelta(seconds=30)


def test_cron_every_five_minutes_lands_on_next_five_minute_mark():
    schedule = parse_schedule("*/5 * * * *")
    # 12:07 -> next fire is 12:10
    after = datetime(2026, 1, 1, 12, 7, 0, tzinfo=UTC)
    assert schedule.next_run_at(after) == datetime(2026, 1, 1, 12, 10, 0, tzinfo=UTC)


def test_daily_shorthand_lands_on_next_midnight():
    schedule = parse_schedule("@daily")
    after = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert schedule.next_run_at(after) == datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC)
