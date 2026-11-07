"""Finds ``@Cron``/``@Interval``/``@Timeout`` methods on providers and registers them; starts and stops the registry
with the application."""

from __future__ import annotations

from austial.core.discovery import DiscoveryService
from austial.schedule.decorators import SCHEDULE_METADATA
from austial.schedule.registry import SchedulerRegistry


class ScheduleExplorer:
    def __init__(self, discovery: DiscoveryService, registry: SchedulerRegistry):
        self.discovery = discovery
        self.registry = registry

    def on_module_init(self) -> None:
        for wrapper, method_name, specs in self.discovery.get_methods_with_metadata(SCHEDULE_METADATA):
            callback = getattr(wrapper.instance, method_name)
            for spec in specs:
                name = spec.name or f"{wrapper.name}.{method_name}"
                if spec.kind == "cron":
                    self.registry.add_cron_job(name, str(spec.value), callback)
                elif spec.kind == "interval":
                    self.registry.add_interval(name, float(spec.value), callback)
                else:
                    self.registry.add_timeout(name, float(spec.value), callback)

    def on_application_bootstrap(self) -> None:
        self.registry.start_all()

    def on_module_destroy(self) -> None:
        self.registry.stop_all()
