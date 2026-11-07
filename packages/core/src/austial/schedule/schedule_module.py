"""``ScheduleModule.for_root()`` -- mirrors ``ScheduleModule.forRoot()``."""

from __future__ import annotations

from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule
from austial.schedule.explorer import ScheduleExplorer
from austial.schedule.registry import SchedulerRegistry


@Module()
class ScheduleModule:
    @staticmethod
    def for_root() -> DynamicModule:
        return DynamicModule(
            module=ScheduleModule,
            providers=[SchedulerRegistry, ScheduleExplorer],
            exports=[SchedulerRegistry],
        )
