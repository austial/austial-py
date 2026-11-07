"""``austial.schedule`` -- in-process task scheduling, mirrors ``@nestjs/schedule``.

from austial.schedule import ScheduleModule, SchedulerRegistry, Cron, Interval, Timeout
"""

from austial.schedule.decorators import Cron, Interval, ScheduleSpec, Timeout
from austial.schedule.explorer import ScheduleExplorer
from austial.schedule.registry import ScheduledJob, ScheduleError, SchedulerRegistry
from austial.schedule.schedule_module import ScheduleModule

__all__ = [
    "Cron",
    "Interval",
    "ScheduleError",
    "ScheduleExplorer",
    "ScheduleModule",
    "ScheduleSpec",
    "ScheduledJob",
    "SchedulerRegistry",
    "Timeout",
]
