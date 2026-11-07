"""Mounts every ``@WebSocketGateway`` provider as a WebSocket route and dispatches messages through
guards, pipes and interceptors."""

from __future__ import annotations

import inspect
import json
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect

from austial.common.decorators.injectable import Inject
from austial.common.exceptions.http_exceptions import HttpException
from austial.common.interceptors.base import CallHandler
from austial.common.logger import Logger
from austial.common.pipes.validation_pipe import ArgumentMetadata
from austial.core.discovery import DiscoveryService
from austial.core.http_adapter_host import HttpAdapterHost
from austial.core.metadata import (
    GUARDS_METADATA,
    INTERCEPTORS_METADATA,
    PIPES_METADATA,
    get_metadata,
)
from austial.core.module_ref import ModuleRef
from austial.websockets.decorators import (
    GATEWAY_METADATA,
    SUBSCRIBE_METADATA,
    ConnectedSocketMarker,
    MessageBodyMarker,
)
from austial.websockets.types import WsClient, WsException, WsExecutionContext, WsResponse, WsServer

_logger = Logger("WebSocketsController")
WS_ADAPTER = "AUSTIAL_WS_ADAPTER"


async def _maybe(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class GatewayRunner:
    def __init__(
        self,
        discovery: DiscoveryService,
        module_ref: ModuleRef,
        host: HttpAdapterHost,
        adapter: Any = Inject(WS_ADAPTER),
    ):
        self.discovery, self.module_ref, self.host = discovery, module_ref, host
        self.adapter = adapter  # None = plain WebSocket frames; a SocketIoAdapter = Socket.IO
        self.servers: dict[type, WsServer] = {}

    # -- wiring -----------------------------------------------------------------------
    async def on_application_bootstrap(self) -> None:
        app = self.host.http_adapter
        if app is None:
            return
        paths: dict[str, type] = {}
        for wrapper in self.discovery.get_providers(GATEWAY_METADATA):
            options = wrapper.get_metadata(GATEWAY_METADATA)
            if options.path in paths:
                raise RuntimeError(f"{wrapper.name} and {paths[options.path].__name__} both listen on {options.path}")
            assert wrapper.metatype is not None
            paths[options.path] = wrapper.metatype
            gateway = self.module_ref.get(wrapper.token)
            if self.adapter is not None:
                server = self.adapter.mount(self, app, options.path, gateway, self._handlers(gateway))
            else:
                server = WsServer()
                app.add_api_websocket_route(options.path, self._endpoint(gateway, server))
            self.servers[type(gateway)] = server
            gateway.server = server
            after_init = getattr(gateway, "after_init", None)
            if callable(after_init):
                await _maybe(after_init(server))

    def _endpoint(self, gateway: Any, server: WsServer):
        handlers = self._handlers(gateway)

        async def endpoint(websocket: WebSocket) -> None:
            await websocket.accept()
            client = WsClient(websocket, server)
            server._add(client)  # noqa: SLF001
            try:
                connect = getattr(gateway, "handle_connection", None)
                if callable(connect):
                    await _maybe(connect(client))
                while True:
                    frame = await websocket.receive()
                    if frame["type"] == "websocket.disconnect":
                        break
                    raw = frame.get("text") or (frame.get("bytes") or b"").decode("utf-8", "replace")
                    await self._dispatch(gateway, handlers, client, raw)
            except WebSocketDisconnect:
                pass
            finally:
                server._remove(client)  # noqa: SLF001
                disconnect = getattr(gateway, "handle_disconnect", None)
                if callable(disconnect):
                    await _maybe(disconnect(client))

        return endpoint

    @staticmethod
    def _handlers(gateway: Any) -> dict[str, Any]:
        found: dict[str, Any] = {}
        for name, member in inspect.getmembers(type(gateway), predicate=callable):
            event = get_metadata(SUBSCRIBE_METADATA, member)
            if event is not None:
                found[event] = getattr(gateway, name)
        return found

    # -- one message ------------------------------------------------------------------
    async def process(
        self, gateway: Any, handler: Any, client: WsClient, event: str, data: Any
    ) -> tuple[str, Any] | None:
        """Runs one message through guards, pipes, interceptors and the handler. Returns what to send back as
        ``(event, payload)``, or ``None`` for silence. Errors become ``exception`` events; the connection survives."""
        try:
            result = await self._run(gateway, handler, client, data)
        except WsException as exc:
            return exc.event, exc.payload
        except HttpException as exc:
            return "exception", {"status": "error", "message": exc.get_response().get("message")}
        except Exception as exc:  # noqa: BLE001 - a handler bug must not drop the connection
            _logger.error(f"Handler for '{event}' raised {type(exc).__name__}: {exc}")
            return "exception", {"status": "error", "message": "Internal server error"}
        if result is None:
            return None
        if isinstance(result, WsResponse):
            return result.event, result.data
        return event, result

    async def _dispatch(self, gateway: Any, handlers: dict[str, Any], client: WsClient, raw: str) -> None:
        try:
            message = json.loads(raw)
            event, data, message_id = message["event"], message.get("data"), message.get("id")
        except (ValueError, KeyError, TypeError):
            await client.send("exception", {"status": "error", "message": 'Expected {"event": ..., "data": ...}'})
            return
        handler = handlers.get(event)
        if handler is None:
            await client.send("exception", {"status": "error", "message": f"Unknown event '{event}'"}, id=message_id)
            return
        reply = await self.process(gateway, handler, client, event, data)
        if reply is not None:
            await client.send(reply[0], reply[1], id=message_id)

    def _components(self, key: str, gateway: Any, handler: Any) -> list[Any]:
        raw = [*get_metadata(key, type(gateway), []), *get_metadata(key, handler, [])]
        return [self.module_ref.get(c) if isinstance(c, type) else c for c in raw]

    async def _run(self, gateway: Any, handler: Any, client: WsClient, data: Any) -> Any:
        context = WsExecutionContext(client, data, type(gateway), handler)
        for guard in self._components(GUARDS_METADATA, gateway, handler):
            if not await _maybe(guard.can_activate(context)):
                raise WsException("Forbidden resource")
        pipes = self._components(PIPES_METADATA, gateway, handler)
        kwargs = await self._arguments(handler, client, data, pipes)

        async def call() -> Any:
            return await _maybe(handler(**kwargs))

        chain = call
        for interceptor in reversed(self._components(INTERCEPTORS_METADATA, gateway, handler)):
            chain = self._wrap(interceptor, context, chain)
        return await chain()

    @staticmethod
    def _wrap(interceptor: Any, context: WsExecutionContext, next_call: Any):
        async def wrapped() -> Any:
            return await interceptor.intercept(context, CallHandler(next_call))

        return wrapped

    async def _arguments(self, handler: Any, client: WsClient, data: Any, pipes: list[Any]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        data_used = False
        try:
            parameters = inspect.signature(handler, eval_str=True).parameters
        except NameError:  # an annotation that can't be resolved here: fall back to the raw strings
            parameters = inspect.signature(handler).parameters
        for name, param in parameters.items():
            default = param.default
            if isinstance(default, ConnectedSocketMarker) or param.annotation is WsClient:
                kwargs[name] = client
                continue
            if isinstance(default, MessageBodyMarker):
                value = data.get(default.key) if default.key and isinstance(data, dict) else data
                local_pipes = [self.module_ref.get(p) if isinstance(p, type) else p for p in default.pipes]
            elif not data_used and default is inspect.Parameter.empty:
                value, local_pipes = data, []
            else:
                continue
            data_used = True
            metadata = ArgumentMetadata(
                type="body", data=default.key if isinstance(default, MessageBodyMarker) else name, metatype=None
            )
            for pipe in [*pipes, *local_pipes]:
                value = await _maybe(pipe.transform(value, metadata))
            kwargs[name] = value
        return kwargs
