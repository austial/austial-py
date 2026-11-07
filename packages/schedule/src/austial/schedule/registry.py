"""``SchedulerRegistry`` -- mirrors ``@nestjs/schedule``'s: add, look up, stop and delete cron jobs,
intervals and timeouts at runtime. The decorators (``@Cron`` ...) register into it on bootstrap.

A job's callback runs *inline* in its loop, so a slow run delays the next one instead of overlapping it.
Exceptions in a callback are logged and the job carries on.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from austial.common.logger import Logger
from austial.jobs.schedule import Schedule, parse_schedule

_logger = Logger("SchedulerRegistry")

Callback = Callable[[], Any]


class ScheduleError(Exception):
    pass


class ScheduledJob:
    """One registered job. ``stop()`` pauses it, ``start()`` resumes (a stopped cron/interval restarts its
    cadence; a timeout restarts its delay)."""

    def __init__(self, registry: SchedulerRegistry, name: str, kind: str, callback: Callback):
        self._registry = registry
        self.name = name
        self.kind = kind  # "cron" | "interval" | "timeout"
        self.callback = callback
        self.schedule: Schedule | None = None
        self.seconds: float = 0.0
        self.runs = 0
        self.done = False  # timeouts: fired
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if not self.running:
            self.done = False
            self._task = asyncio.get_running_loop().create_task(self._registry._run(self))  # noqa: SLF001

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def next_run(self) -> datetime | None:
        """Next fire time for cron jobs (``None`` for other kinds)."""
        return self.schedule.next_run_at(self._registry.clock()) if self.schedule else None


class SchedulerRegistry:
    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.clock = clock
        self._sleep = sleep
        self._jobs: dict[str, dict[str, ScheduledJob]] = {"cron": {}, "interval": {}, "timeout": {}}
        self._started = False

    # -- adding -----------------------------------------------------------------------
    def _add(self, kind: str, name: str, callback: Callback) -> ScheduledJob:
        if name in self._jobs[kind]:
            raise ScheduleError(f"A {kind} job named '{name}' already exists")
        job = ScheduledJob(self, name, kind, callback)
        self._jobs[kind][name] = job
        return job

    def add_cron_job(self, name: str, schedule: str, callback: Callback) -> ScheduledJob:
        """``schedule`` is 5-field cron, ``@hourly``/``@daily``/..., or ``@every 30s``/``5m``/``2h``."""
        parsed = parse_schedule(schedule)  # validate first: a bad schedule registers nothing
        job = self._add("cron", name, callback)
        job.schedule = parsed
        if self._started:
            job.start()
        return job

    def add_interval(self, name: str, seconds: float, callback: Callback) -> ScheduledJob:
        if seconds <= 0:
            raise ScheduleError("An interval must be positive")
        job = self._add("interval", name, callback)
        job.seconds = seconds
        if self._started:
            job.start()
        return job

    def add_timeout(self, name: str, seconds: float, callback: Callback) -> ScheduledJob:
        if seconds < 0:
            raise ScheduleError("A timeout can't be negative")
        job = self._add("timeout", name, callback)
        job.seconds = seconds
        if self._started:
            job.start()
        return job

    # -- looking up / deleting --------------------------------------------------------
    def _get(self, kind: str, name: str) -> ScheduledJob:
        try:
            return self._jobs[kind][name]
        except KeyError:
            raise ScheduleError(f"No {kind} job named '{name}'") from None

    def _delete(self, kind: str, name: str) -> None:
        self._get(kind, name).stop()
        del self._jobs[kind][name]

    def get_cron_job(self, name: str) -> ScheduledJob:
        return self._get("cron", name)

    def get_interval(self, name: str) -> ScheduledJob:
        return self._get("interval", name)

    def get_timeout(self, name: str) -> ScheduledJob:
        return self._get("timeout", name)

    def get_cron_jobs(self) -> dict[str, ScheduledJob]:
        return dict(self._jobs["cron"])

    def get_intervals(self) -> list[str]:
        return list(self._jobs["interval"])

    def get_timeouts(self) -> list[str]:
        return list(self._jobs["timeout"])

    def delete_cron_job(self, name: str) -> None:
        self._delete("cron", name)

    def delete_interval(self, name: str) -> None:
        self._delete("interval", name)

    def delete_timeout(self, name: str) -> None:
        self._delete("timeout", name)

    # -- lifecycle --------------------------------------------------------------------
    def start_all(self) -> None:
        self._started = True
        for jobs in self._jobs.values():
            for job in jobs.values():
                job.start()

    def stop_all(self) -> None:
        self._started = False
        for jobs in self._jobs.values():
            for job in jobs.values():
                job.stop()

    # -- the loops --------------------------------------------------------------------
    async def _run(self, job: ScheduledJob) -> None:
        if job.kind == "timeout":
            await self._sleep(job.seconds)
            await self._fire(job)
            job.done = True
            return
        while True:
            if job.kind == "interval":
                await self._sleep(job.seconds)
            else:
                assert job.schedule is not None
                now = self.clock()
                await self._sleep(max(0.0, (job.schedule.next_run_at(now) - now).total_seconds()))
            await self._fire(job)

    async def _fire(self, job: ScheduledJob) -> None:
        job.runs += 1
        try:
            result = job.callback()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:  # noqa: BLE001 - one bad run must not kill the schedule
            _logger.error(f"{job.kind} job '{job.name}' raised {type(exc).__name__}: {exc}")
