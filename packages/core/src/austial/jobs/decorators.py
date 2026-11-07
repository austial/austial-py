"""``@Cron(...)`` and ``@Job(...)`` -- metadata decorators the ``JobRegistry`` reads.

``@Cron`` marks an injectable method as a scheduled job; the ``Worker`` fires it on
its schedule. ``@Job`` marks it as enqueueable via ``JobQueue.enqueue(name, ...)``.

A single method may carry both decorators (a cron that can also be triggered
manually) since they set independent metadata keys.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from austial.core.metadata import set_metadata

CRON_METADATA = "austial:jobs:cron"
JOB_METADATA = "austial:jobs:job"


@dataclass(frozen=True, slots=True)
class CronSpec:
    """Attached to a method by ``@Cron``. Read by :class:`JobRegistry.discover`."""

    schedule: str
    name: str | None = None
    jitter_seconds: int = 0


@dataclass(frozen=True, slots=True)
class JobSpec:
    """Attached to a method by ``@Job``. Read by :class:`JobRegistry.discover`."""

    name: str
    max_attempts: int = 3
    backoff_seconds: int = 30
    idempotent: bool = True


def Cron(schedule: str, *, name: str | None = None, jitter_seconds: int = 0) -> Callable:  # noqa: N802
    """Mark a method as a scheduled job.

    Example::

        @Injectable()
        class Reports:
            @Cron("@daily")
            async def daily_snapshot(self) -> None: ...

            @Cron("*/5 * * * *", name="poll-feed")
            async def poll(self) -> None: ...

    ``schedule`` accepts standard 5-field cron (``"*/5 * * * *"``) or shorthand
    (``"@hourly"`` / ``"@daily"`` / ``"@every 30s"``). ``jitter_seconds`` adds a
    uniform random offset up to that many seconds to each scheduled fire time,
    useful for smearing peaks across a fleet of workers."""

    def decorator(fn):
        set_metadata(CRON_METADATA, CronSpec(schedule=schedule, name=name, jitter_seconds=jitter_seconds))(fn)
        return fn

    return decorator


def Job(  # noqa: N802
    name: str,
    *,
    max_attempts: int = 3,
    backoff_seconds: int = 30,
    idempotent: bool = True,
) -> Callable:
    """Mark a method as an enqueueable job.

    Example::

        @Injectable()
        class Payments:
            @Job("send-remittance", max_attempts=5, backoff_seconds=60)
            async def send(self, *, remittance_id: str) -> None: ...

    ``max_attempts`` includes the first attempt; ``backoff_seconds`` is the base
    for exponential backoff between retries. ``idempotent`` is a hint to the
    queue that ``idempotency_key`` deduplication is safe for this handler."""

    def decorator(fn):
        set_metadata(
            JOB_METADATA,
            JobSpec(name=name, max_attempts=max_attempts, backoff_seconds=backoff_seconds, idempotent=idempotent),
        )(fn)
        return fn

    return decorator
