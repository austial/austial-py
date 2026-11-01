"""``austial.jobs`` -- background-job runner.

Ships a ``JobsModule.for_root(...)`` dynamic module, a ``JobQueue`` (enqueue /
cancel / status), a ``Worker`` (background loop with retry + exponential
backoff), ``@Cron`` and ``@Job`` decorators, a pluggable ``JobBackend``
protocol (the in-memory reference impl runs out of the box), and a jobs-
scoped ``IdempotencyStore`` (independent from ``austial.security``'s own).

The design mirrors ``@nestjs/schedule`` + BullMQ: framework provides the
scheduler, the queue and the worker; product code declares handlers on
``@Injectable`` classes with ``@Cron("@daily")`` / ``@Job("send-email")``.
Redis / Arq / Dramatiq wiring is deferred -- the in-memory backend is a drop-
in replacement for tests and single-node deployments; product code swaps it
via ``JobsModule.for_root(config, backend=MyBackend())``.
"""

from austial.jobs.backend import InMemoryJobBackend, JobBackend
from austial.jobs.config import JobsConfig
from austial.jobs.decorators import (
    CRON_METADATA,
    JOB_METADATA,
    Cron,
    CronSpec,
    Job,
    JobSpec,
)
from austial.jobs.errors import (
    InvalidScheduleError,
    JobError,
    JobExecutionError,
    UnknownJobError,
)
from austial.jobs.idempotency import IdempotencyStore, InMemoryIdempotencyStore
from austial.jobs.jobs_module import JobsModule
from austial.jobs.queue import JobQueue
from austial.jobs.records import JobRecord, JobStatus
from austial.jobs.registry import CronEntry, JobEntry, JobRegistry
from austial.jobs.schedule import Schedule, parse_schedule
from austial.jobs.worker import Worker

__all__ = [
    "CRON_METADATA",
    "Cron",
    "CronEntry",
    "CronSpec",
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
    "InMemoryJobBackend",
    "InvalidScheduleError",
    "JOB_METADATA",
    "Job",
    "JobBackend",
    "JobEntry",
    "JobError",
    "JobExecutionError",
    "JobQueue",
    "JobRecord",
    "JobRegistry",
    "JobSpec",
    "JobStatus",
    "JobsConfig",
    "JobsModule",
    "Schedule",
    "UnknownJobError",
    "Worker",
    "parse_schedule",
]
