"""``EventEmitter`` -- mirrors ``@nestjs/event-emitter``'s ``EventEmitter2``.

Events are dot-separated names (``order.created``). A *listener* may use wildcards when
``wildcard=True``: ``*`` matches exactly one segment, ``**`` any number (``order.*``, ``**.failed``).
Handlers can be plain functions or coroutines.

* ``emit(event, *args)`` -- fire and forget. Sync handlers run immediately; async handlers are
  scheduled on the running loop. Returns whether anyone was listening.
* ``await emit_async(event, *args)`` -- runs every handler and awaits them all; returns their results.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from austial.common.logger import Logger

_logger = Logger("EventEmitter")


@dataclass
class EventEmitterOptions:
    wildcard: bool = True
    delimiter: str = "."
    max_listeners: int | None = None  # per event pattern; None = unlimited
    suppress_errors: bool = True  # default for handlers: log instead of raising


@dataclass
class _Listener:
    pattern: str
    handler: Callable[..., Any]
    once: bool
    suppress_errors: bool


def _matches(pattern: list[str], event: list[str]) -> bool:
    if not pattern:
        return not event
    head, rest = pattern[0], pattern[1:]
    if head == "**":
        return any(_matches(rest, event[i:]) for i in range(len(event) + 1))
    if not event:
        return False
    return (head == "*" or head == event[0]) and _matches(rest, event[1:])


class EventEmitter:
    def __init__(self, options: EventEmitterOptions | None = None):
        self.options = options or EventEmitterOptions()
        self._listeners: list[_Listener] = []
        self._tasks: set[asyncio.Task[Any]] = set()

    # -- registration -----------------------------------------------------------------
    def on(
        self,
        event: str,
        handler: Callable[..., Any],
        *,
        prepend: bool = False,
        once: bool = False,
        suppress_errors: bool | None = None,
    ) -> Callable[[], None]:
        """Subscribes ``handler`` to ``event`` (a pattern, if wildcards are on). Returns a function that
        unsubscribes it again."""
        limit = self.options.max_listeners
        if limit is not None and sum(1 for lst in self._listeners if lst.pattern == event) >= limit:
            raise RuntimeError(f"Too many listeners for '{event}' (max {limit}): likely a leak")
        listener = _Listener(
            event,
            handler,
            once,
            self.options.suppress_errors if suppress_errors is None else suppress_errors,
        )
        if prepend:
            self._listeners.insert(0, listener)
        else:
            self._listeners.append(listener)
        return lambda: self._remove(listener)

    def once(self, event: str, handler: Callable[..., Any], **kwargs: Any) -> Callable[[], None]:
        return self.on(event, handler, once=True, **kwargs)

    def off(self, event: str, handler: Callable[..., Any]) -> None:
        for listener in list(self._listeners):
            if listener.pattern == event and listener.handler == handler:
                self._remove(listener)

    def remove_all_listeners(self, event: str | None = None) -> None:
        self._listeners = [lst for lst in self._listeners if event is not None and lst.pattern != event]

    def listeners(self, event: str) -> list[Callable[..., Any]]:
        return [lst.handler for lst in self._matching(event)]

    def listener_count(self, event: str) -> int:
        return len(self._matching(event))

    def _remove(self, listener: _Listener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _matching(self, event: str) -> list[_Listener]:
        delimiter = self.options.delimiter
        parts = event.split(delimiter)
        found = []
        for listener in self._listeners:
            if listener.pattern == event or (
                self.options.wildcard and _matches(listener.pattern.split(delimiter), parts)
            ):
                found.append(listener)
        return found

    # -- emitting ---------------------------------------------------------------------
    def emit(self, event: str, *args: Any) -> bool:
        """Calls every matching listener. Async handlers need a running event loop and run in the
        background; their failures are logged (or, with ``suppress_errors=False``, logged as errors too:
        there is no caller to raise to -- use :meth:`emit_async` for that)."""
        matching = self._matching(event)
        for listener in matching:
            if listener.once:
                self._remove(listener)
            try:
                result = listener.handler(*args)
            except Exception as exc:  # noqa: BLE001 - a handler failure must not break the emitter
                if not listener.suppress_errors:
                    raise
                _logger.error(f"Handler for '{event}' raised {type(exc).__name__}: {exc}")
                continue
            if inspect.isawaitable(result):
                self._schedule(event, result)
        return bool(matching)

    def _schedule(self, event: str, awaitable: Any) -> None:
        async def run() -> None:
            try:
                await awaitable
            except Exception as exc:  # noqa: BLE001
                _logger.error(f"Async handler for '{event}' raised {type(exc).__name__}: {exc}")

        task = asyncio.get_running_loop().create_task(run())
        self._tasks.add(task)  # keep a reference so the task isn't garbage-collected mid-flight
        task.add_done_callback(self._tasks.discard)

    async def emit_async(self, event: str, *args: Any) -> list[Any]:
        """Runs every matching listener (async ones concurrently) and returns their results, in
        listener order. A listener registered with ``suppress_errors=True`` (the default) that raises
        contributes ``None`` and is logged; with ``False`` the exception propagates."""
        matching = self._matching(event)
        for listener in matching:
            if listener.once:
                self._remove(listener)

        async def invoke(listener: _Listener) -> Any:
            try:
                result = listener.handler(*args)
                return await result if inspect.isawaitable(result) else result
            except Exception as exc:  # noqa: BLE001
                if not listener.suppress_errors:
                    raise
                _logger.error(f"Handler for '{event}' raised {type(exc).__name__}: {exc}")
                return None

        return list(await asyncio.gather(*(invoke(listener) for listener in matching)))

    async def wait_idle(self) -> None:
        """Waits for background handlers started by :meth:`emit` -- handy in tests and on shutdown."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
