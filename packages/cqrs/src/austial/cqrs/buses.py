"""``CommandBus``, ``QueryBus`` and ``EventBus`` -- mirror ``@nestjs/cqrs``.

* A **command** asks for a change and has exactly one handler; ``await commands.execute(cmd)`` returns its result.
* A **query** asks for data and has exactly one handler; ``await queries.execute(q)``.
* An **event** says something happened and has any number of handlers (and sagas); ``await events.publish(e)``.

Commands, queries and events are plain classes -- dataclasses are ideal.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Iterable
from typing import Any

from austial.common.logger import Logger

_logger = Logger("EventBus")


class HandlerNotFoundError(Exception):
    def __init__(self, kind: str, message: Any):
        name = type(message).__name__
        super().__init__(
            f"No {kind} handler is registered for {name}. Decorate a provider with @{kind.title()}Handler({name})."
        )
        self.message = message


class DuplicateHandlerError(Exception):
    pass


async def _call(fn: Callable[..., Any], *args: Any) -> Any:
    result = fn(*args)
    return await result if inspect.isawaitable(result) else result


class _HandlerBus:
    kind = ""
    method = "execute"

    def __init__(self) -> None:
        self._handlers: dict[type, Any] = {}

    def register(self, message_type: type, handler: Any) -> None:
        if message_type in self._handlers:
            raise DuplicateHandlerError(f"{message_type.__name__} already has a {self.kind} handler")
        self._handlers[message_type] = handler

    def has_handler(self, message_type: type) -> bool:
        return message_type in self._handlers

    async def execute(self, message: Any) -> Any:
        handler = self._handlers.get(type(message))
        if handler is None:
            raise HandlerNotFoundError(self.kind, message)
        return await _call(getattr(handler, self.method), message)


class CommandBus(_HandlerBus):
    kind = "command"


class QueryBus(_HandlerBus):
    kind = "query"


class EventBus:
    """Delivers each event to every handler registered for its type (or a base class of it) and then to the
    sagas, which may answer with follow-up commands. Handlers run concurrently; one failing doesn't stop the others
    (it is logged), unless ``raise_errors=True``."""

    def __init__(self, command_bus: CommandBus, *, raise_errors: bool = False) -> None:
        self.command_bus = command_bus
        self.raise_errors = raise_errors
        self._handlers: list[tuple[type, Any]] = []
        self._sagas: list[Callable[[Any], Any]] = []

    def register(self, event_type: type, handler: Any) -> None:
        self._handlers.append((event_type, handler))

    def register_saga(self, saga: Callable[[Any], Any]) -> None:
        """``saga(event)`` returns a command, a list of commands, or ``None``; the commands are executed."""
        self._sagas.append(saga)

    async def publish(self, event: Any) -> None:
        async def deliver(handler: Any) -> None:
            await _call(handler.handle, event)

        matching = [handler for event_type, handler in self._handlers if isinstance(event, event_type)]
        outcomes = await asyncio.gather(*(deliver(h) for h in matching), return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, Exception):
                if self.raise_errors:
                    raise outcome
                _logger.error(f"Handler for {type(event).__name__} raised {type(outcome).__name__}: {outcome}")
        await self._run_sagas(event)

    async def publish_all(self, events: Iterable[Any]) -> None:
        for event in events:
            await self.publish(event)

    async def _run_sagas(self, event: Any) -> None:
        for saga in self._sagas:
            try:
                produced = await _call(saga, event)
                if produced is None:
                    continue
                for command in produced if isinstance(produced, list | tuple) else [produced]:
                    await self.command_bus.execute(command)
            except Exception as exc:  # noqa: BLE001
                if self.raise_errors:
                    raise
                _logger.error(f"Saga raised {type(exc).__name__}: {exc}")
