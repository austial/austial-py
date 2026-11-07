from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from austial import AustialFactory, Injectable, Module
from austial.jobs.errors import InvalidScheduleError
from austial.schedule import Cron, Interval, ScheduleError, ScheduleModule, SchedulerRegistry, Timeout


class FakeTime:
    """A clock whose sleep() advances it instantly, so cron cadence is testable without waiting."""

    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 8, 59, 30, tzinfo=UTC)
        self.sleeps: list[float] = []

    def clock(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)
        await asyncio.sleep(0)  # yield so other tasks and cancellation can run


async def settle(times: int = 20) -> None:
    for _ in range(times):
        await asyncio.sleep(0)


def make() -> tuple[SchedulerRegistry, FakeTime]:
    fake = FakeTime()
    return SchedulerRegistry(clock=fake.clock, sleep=fake.sleep), fake


async def test_interval_fires_repeatedly_at_its_cadence() -> None:
    registry, fake = make()
    calls: list[int] = []
    job = registry.add_interval("tick", 10, lambda: calls.append(1))
    registry.start_all()
    await settle()
    registry.stop_all()
    assert job.runs >= 3 and len(calls) == job.runs
    assert set(fake.sleeps) == {10}  # every wait was exactly the interval


async def test_cron_waits_until_the_next_matching_time_then_follows_the_cadence() -> None:
    registry, fake = make()  # clock starts 08:59:30
    fired_at: list[datetime] = []
    registry.add_cron_job("nine", "0 9 * * *", lambda: fired_at.append(fake.now))
    registry.start_all()
    await settle(8)
    registry.stop_all()
    assert fake.sleeps[0] == 30  # first wait: 08:59:30 -> 09:00:00
    assert fired_at[0] == datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    assert fake.sleeps[1] == 24 * 3600 - 0  # then a full day to the next 09:00
    assert registry.get_cron_job("nine").next_run() is not None


async def test_at_every_schedule_and_cron_validation() -> None:
    registry, fake = make()
    job = registry.add_cron_job("fast", "@every 5s", lambda: None)
    registry.start_all()
    await settle()
    registry.stop_all()
    assert job.runs >= 2 and set(fake.sleeps) == {5}
    with pytest.raises(InvalidScheduleError):
        registry.add_cron_job("bad", "not a schedule", lambda: None)
    assert "bad" not in registry.get_cron_jobs()  # nothing half-registered


async def test_timeout_fires_once_and_is_done() -> None:
    registry, fake = make()
    calls: list[int] = []
    job = registry.add_timeout("once", 7, lambda: calls.append(1))
    registry.start_all()
    await settle()
    assert calls == [1] and job.done and not job.running and fake.sleeps == [7]


async def test_async_callbacks_and_failures_do_not_stop_the_job() -> None:
    registry, _ = make()
    calls = {"n": 0}

    async def flaky() -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first run explodes")

    job = registry.add_interval("flaky", 1, flaky)
    registry.start_all()
    await settle()
    registry.stop_all()
    assert job.runs >= 3  # kept going after the exception


async def test_runtime_add_stop_start_delete_and_lookup() -> None:
    registry, _ = make()
    registry.start_all()  # started registry: new jobs begin straight away
    hits: list[int] = []
    job = registry.add_interval("late", 1, lambda: hits.append(1))
    await settle(6)
    assert job.running and hits

    job.stop()
    count = len(hits)
    await settle(6)
    assert not job.running and len(hits) == count  # paused
    job.start()
    await settle(6)
    assert len(hits) > count  # resumed

    assert registry.get_intervals() == ["late"] and registry.get_interval("late") is job
    registry.add_timeout("t", 1, lambda: None)
    assert registry.get_timeouts() == ["t"]
    registry.delete_interval("late")
    registry.delete_timeout("t")
    assert registry.get_intervals() == [] and not job.running
    registry.stop_all()


def test_registry_errors() -> None:
    registry, _ = make()
    registry.add_interval("x", 1, lambda: None)
    with pytest.raises(ScheduleError, match="already exists"):
        registry.add_interval("x", 1, lambda: None)
    with pytest.raises(ScheduleError, match="No interval"):
        registry.get_interval("missing")
    with pytest.raises(ScheduleError, match="positive"):
        registry.add_interval("neg", 0, lambda: None)
    with pytest.raises(ScheduleError, match="negative"):
        registry.add_timeout("neg", -1, lambda: None)
    with pytest.raises(ScheduleError):
        registry.delete_cron_job("missing")


# -- decorators + module -------------------------------------------------------------------

RUNS: list[str] = []


@Injectable()
class Reports:
    @Cron("@every 1s", name="every-second")
    def every_second(self) -> None:
        RUNS.append("cron")

    @Interval(0.01)
    async def poll(self) -> None:
        RUNS.append("interval")

    @Timeout(0.01)
    def warm_up(self) -> None:
        RUNS.append("timeout")

    @Interval(0.02, name="second-name")
    @Timeout(0.02, name="and-a-timeout")
    def stacked(self) -> None:
        RUNS.append("stacked")


@Module(imports=[ScheduleModule.for_root()], providers=[Reports])
class ScheduledApp:
    pass


async def test_decorated_methods_register_run_on_bootstrap_and_stop_on_close() -> None:
    RUNS.clear()
    app = AustialFactory.create(ScheduledApp)
    registry = app.get(SchedulerRegistry)
    await app.init()
    assert registry.get_cron_jobs().keys() == {"every-second"}
    assert set(registry.get_intervals()) == {"Reports.poll", "second-name"}
    assert set(registry.get_timeouts()) == {"Reports.warm_up", "and-a-timeout"}

    for _ in range(100):
        if {"interval", "timeout", "stacked"} <= set(RUNS):
            break
        await asyncio.sleep(0.01)
    assert {"interval", "timeout", "stacked"} <= set(RUNS)

    await app.close()
    seen = len(RUNS)
    await asyncio.sleep(0.06)
    assert len(RUNS) == seen  # everything stopped with the application
    assert not registry.get_interval("Reports.poll").running
