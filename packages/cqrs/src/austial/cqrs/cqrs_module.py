"""``CqrsModule.for_root()`` -- mirrors ``CqrsModule.forRoot()``."""

from __future__ import annotations

from austial.common.decorators.modules import Module
from austial.core.discovery import DiscoveryService
from austial.core.dynamic_module import DynamicModule
from austial.core.module_ref import ModuleRef
from austial.cqrs.aggregate import EventPublisher
from austial.cqrs.buses import CommandBus, EventBus, QueryBus
from austial.cqrs.decorators import (
    COMMAND_HANDLER_METADATA,
    EVENTS_HANDLER_METADATA,
    QUERY_HANDLER_METADATA,
    SAGA_METADATA,
)


class CqrsExplorer:
    """On bootstrap, finds the decorated handlers and sagas and plugs them into the buses."""

    def __init__(
        self,
        discovery: DiscoveryService,
        module_ref: ModuleRef,
        commands: CommandBus,
        queries: QueryBus,
        events: EventBus,
    ):
        self.discovery, self.module_ref = discovery, module_ref
        self.commands, self.queries, self.events = commands, queries, events

    def on_application_bootstrap(self) -> None:
        for wrapper in self.discovery.get_providers(COMMAND_HANDLER_METADATA):
            self.commands.register(wrapper.get_metadata(COMMAND_HANDLER_METADATA), self.module_ref.get(wrapper.token))
        for wrapper in self.discovery.get_providers(QUERY_HANDLER_METADATA):
            self.queries.register(wrapper.get_metadata(QUERY_HANDLER_METADATA), self.module_ref.get(wrapper.token))
        for wrapper in self.discovery.get_providers(EVENTS_HANDLER_METADATA):
            handler = self.module_ref.get(wrapper.token)
            for event_type in wrapper.get_metadata(EVENTS_HANDLER_METADATA):
                self.events.register(event_type, handler)
        for wrapper, method_name, _ in self.discovery.get_methods_with_metadata(SAGA_METADATA):
            self.events.register_saga(getattr(wrapper.instance, method_name))


@Module()
class CqrsModule:
    @staticmethod
    def for_root(*, raise_event_errors: bool = False) -> DynamicModule:
        """``raise_event_errors=True`` makes ``EventBus.publish`` raise a handler's exception instead of logging it."""
        return DynamicModule(
            module=CqrsModule,
            providers=[
                CommandBus,
                QueryBus,
                {
                    "provide": EventBus,
                    "useFactory": lambda commands: EventBus(commands, raise_errors=raise_event_errors),
                    "inject": [CommandBus],
                },
                EventPublisher,
                CqrsExplorer,
            ],
            exports=[CommandBus, QueryBus, EventBus, EventPublisher],
        )
