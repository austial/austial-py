"""``EventEmitterModule.for_root(...)`` -- mirrors ``EventEmitterModule.forRoot()``."""

from __future__ import annotations

from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule
from austial.events.emitter import EventEmitter, EventEmitterOptions
from austial.events.subscribers_loader import EventSubscribersLoader


@Module()
class EventEmitterModule:
    @staticmethod
    def for_root(
        *,
        wildcard: bool = True,
        delimiter: str = ".",
        max_listeners: int | None = None,
        suppress_errors: bool = True,
    ) -> DynamicModule:
        options = EventEmitterOptions(
            wildcard=wildcard, delimiter=delimiter, max_listeners=max_listeners, suppress_errors=suppress_errors
        )
        return DynamicModule(
            module=EventEmitterModule,
            providers=[
                {"provide": EventEmitterOptions, "useValue": options},
                EventEmitter,
                EventSubscribersLoader,
            ],
            exports=[EventEmitter],
        )
