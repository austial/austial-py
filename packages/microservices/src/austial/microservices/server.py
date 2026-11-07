"""Dispatches transport messages to ``@MessagePattern`` / ``@EventPattern`` handlers found on providers and
controllers, through guards, pipes and interceptors."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from austial.common.guards.base import ExecutionContext
from austial.common.interceptors.base import CallHandler
from austial.common.logger import Logger
from austial.common.pipes.validation_pipe import ArgumentMetadata
from austial.core.discovery import DiscoveryService
from austial.core.metadata import GUARDS_METADATA, INTERCEPTORS_METADATA, PIPES_METADATA, get_metadata
from austial.core.module_ref import ModuleRef
from austial.microservices.decorators import (
    EVENT_PATTERN_METADATA,
    MESSAGE_PATTERN_METADATA,
    CtxMarker,
    PayloadMarker,
)
from austial.microservices.transport import RpcException, ServerTransport, pattern_key

_logger = Logger("MicroserviceServer")


@dataclass
class RpcContext:
    pattern: str
    kind: str  # "request" | "event"


class RpcExecutionContext(ExecutionContext):
    """``get_type()`` is ``"rpc"``; ``switch_to_rpc()`` gives the data and the :class:`RpcContext`."""

    def __init__(self, data: Any, rpc: RpcContext, controller_class: type, handler: Any):
        super().__init__(None, controller_class, handler)  # type: ignore[arg-type]
        self._data, self._rpc = data, rpc

    def get_type(self) -> str:
        return "rpc"

    def switch_to_rpc(self) -> RpcExecutionContext:
        return self

    def get_data(self) -> Any:
        return self._data

    def get_context(self) -> RpcContext:
        return self._rpc

    def switch_to_http(self) -> ExecutionContext:
        raise NotImplementedError("This is an RPC execution context: use switch_to_rpc().")


async def _maybe(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class HandlerRegistry:
    """All the handlers of one application, discovered from its providers and controllers."""

    def __init__(self, discovery: DiscoveryService, module_ref: ModuleRef):
        self.discovery, self.module_ref = discovery, module_ref
        self._messages: dict[str, tuple[Any, Any]] = {}
        self._events: dict[str, list[tuple[Any, Any]]] = {}
        self._built = False

    def build(self) -> None:
        if self._built:
            return
        self._built = True
        for controllers in (False, True):
            for wrapper, name, pattern in self.discovery.get_methods_with_metadata(
                MESSAGE_PATTERN_METADATA, controllers=controllers
            ):
                key = pattern_key(pattern)
                if key in self._messages:
                    raise RuntimeError(f"Two handlers for the message pattern {key}")
                self._messages[key] = (wrapper.instance, getattr(wrapper.instance, name))
            for wrapper, name, patterns in self.discovery.get_methods_with_metadata(
                EVENT_PATTERN_METADATA, controllers=controllers
            ):
                for pattern in patterns:
                    self._events.setdefault(pattern_key(pattern), []).append(
                        (wrapper.instance, getattr(wrapper.instance, name))
                    )

    def patterns(self) -> dict[str, list[str]]:
        """The pattern keys this application handles, for transports that must subscribe to topics up front."""
        self.build()
        return {"request": list(self._messages), "event": list(self._events)}

    async def handle(self, kind: str, pattern: str, data: Any) -> Any:
        self.build()
        context = RpcContext(pattern, kind)
        if kind == "event":
            for owner, handler in self._events.get(pattern, []):
                try:
                    await self._run(owner, handler, data, context)
                except Exception as exc:  # noqa: BLE001
                    _logger.error(f"Event handler for {pattern} raised {type(exc).__name__}: {exc}")
            return None
        entry = self._messages.get(pattern)
        if entry is None:
            raise RpcException(f"There is no matching message handler for {pattern}")
        owner, handler = entry
        return await self._run(owner, handler, data, context)

    def _components(self, key: str, owner: Any, handler: Any) -> list[Any]:
        raw = [*get_metadata(key, type(owner), []), *get_metadata(key, handler, [])]
        return [self.module_ref.get(c) if isinstance(c, type) else c for c in raw]

    async def _run(self, owner: Any, handler: Any, data: Any, rpc: RpcContext) -> Any:
        context = RpcExecutionContext(data, rpc, type(owner), handler)
        for guard in self._components(GUARDS_METADATA, owner, handler):
            if not await _maybe(guard.can_activate(context)):
                raise RpcException("Forbidden resource")
        pipes = self._components(PIPES_METADATA, owner, handler)
        kwargs: dict[str, Any] = {}
        data_used = False
        for name, param in inspect.signature(handler, eval_str=True).parameters.items():
            default = param.default
            if isinstance(default, CtxMarker):
                kwargs[name] = rpc
                continue
            if isinstance(default, PayloadMarker):
                value = data.get(default.key) if default.key and isinstance(data, dict) else data
            elif not data_used and default is inspect.Parameter.empty:
                value = data
            else:
                continue
            data_used = True
            for pipe in pipes:
                value = await _maybe(pipe.transform(value, ArgumentMetadata(type="body", data=name, metatype=None)))
            kwargs[name] = value

        async def call() -> Any:
            return await _maybe(handler(**kwargs))

        chain = call
        for interceptor in reversed(self._components(INTERCEPTORS_METADATA, owner, handler)):
            chain = _wrap(interceptor, context, chain)
        return await chain()


def _wrap(interceptor: Any, context: RpcExecutionContext, next_call: Any):
    async def wrapped() -> Any:
        return await interceptor.intercept(context, CallHandler(next_call))

    return wrapped


class MicroserviceServer:
    """A transport plus the application's handlers. ``await start()`` / ``await stop()``."""

    def __init__(self, transport: ServerTransport, registry: HandlerRegistry):
        self.transport, self.registry = transport, registry
        self.running = False

    async def start(self) -> None:
        if self.running:
            return
        self.transport.patterns = self.registry.patterns()
        await self.transport.listen(self.registry.handle)
        self.running = True

    async def stop(self) -> None:
        if self.running:
            await self.transport.close()
            self.running = False
