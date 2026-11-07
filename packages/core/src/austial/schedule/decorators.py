"""``@Cron``, ``@Interval`` and ``@Timeout`` -- mirror ``@nestjs/schedule``.

::

    @Injectable()
    class Reports:
        @Cron("0 9 * * 1-5")                 # weekdays at 09:00 UTC (5-field cron, @daily, @every 30s ...)
        async def morning(self): ...

        @Interval(30)                         # every 30 seconds
        async def poll(self): ...

        @Timeout(5)                           # once, 5 seconds after startup
        def warm_up(self): ...

Pass ``name="..."`` to find the job later in the ``SchedulerRegistry``; the default is ``Class.method``.
(Not to be confused with ``austial.jobs.Cron``, which enqueues durable, database-backed jobs.)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from austial.core.metadata import get_metadata, set_metadata

SCHEDULE_METADATA = "austial:schedule"


@dataclass(frozen=True)
class ScheduleSpec:
    kind: str  # "cron" | "interval" | "timeout"
    value: str | float  # cron string, or seconds
    name: str | None = None


def _decorator(spec: ScheduleSpec) -> Callable:
    def decorator(fn):
        existing = list(get_metadata(SCHEDULE_METADATA, fn, []))
        set_metadata(SCHEDULE_METADATA, [*existing, spec])(fn)
        return fn

    return decorator


def Cron(schedule: str, *, name: str | None = None) -> Callable:  # noqa: N802
    return _decorator(ScheduleSpec("cron", schedule, name))


def Interval(seconds: float, *, name: str | None = None) -> Callable:  # noqa: N802
    return _decorator(ScheduleSpec("interval", seconds, name))


def Timeout(seconds: float, *, name: str | None = None) -> Callable:  # noqa: N802
    return _decorator(ScheduleSpec("timeout", seconds, name))
