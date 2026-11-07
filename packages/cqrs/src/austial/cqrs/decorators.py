"""``@CommandHandler``, ``@QueryHandler``, ``@EventsHandler`` and ``@Saga`` -- mirror ``@nestjs/cqrs``."""

from __future__ import annotations

from collections.abc import Callable

from austial.core.metadata import set_metadata

COMMAND_HANDLER_METADATA = "austial:cqrs:command_handler"
QUERY_HANDLER_METADATA = "austial:cqrs:query_handler"
EVENTS_HANDLER_METADATA = "austial:cqrs:events_handler"
SAGA_METADATA = "austial:cqrs:saga"


def CommandHandler(command: type) -> Callable:  # noqa: N802
    """Class decorator: this provider handles ``command`` via ``async def execute(self, command)``."""
    return set_metadata(COMMAND_HANDLER_METADATA, command)


def QueryHandler(query: type) -> Callable:  # noqa: N802
    """Class decorator: this provider answers ``query`` via ``async def execute(self, query)``."""
    return set_metadata(QUERY_HANDLER_METADATA, query)


def EventsHandler(*events: type) -> Callable:  # noqa: N802
    """Class decorator: this provider reacts to ``events`` via ``async def handle(self, event)``."""
    return set_metadata(EVENTS_HANDLER_METADATA, list(events))


def Saga() -> Callable:  # noqa: N802
    """Method decorator: ``def saga(self, event) -> Command | list[Command] | None`` is called for every published
    event and the commands it returns are executed. (NestJS sagas map an RxJS stream; here it is event -> commands.)"""
    return set_metadata(SAGA_METADATA, True)
