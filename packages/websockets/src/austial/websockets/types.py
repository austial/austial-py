"""Gateway-side types: the client wrapper, the server (broadcast + rooms) and the message helpers."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocket, WebSocketState

from austial.common.guards.base import ExecutionContext


class WsException(Exception):
    """Raise from a handler to answer the client with an ``exception`` event instead of closing anything."""

    def __init__(self, message: str | dict, event: str = "exception"):
        self.payload = message if isinstance(message, dict) else {"status": "error", "message": message}
        self.event = event
        super().__init__(str(message))


@dataclass
class WsResponse:
    """Return from a handler to choose the event name of the reply (default: the event that was received)."""

    event: str
    data: Any = None


class WsClient:
    """One connected socket. ``data`` is free storage for your own per-connection state (the user, ...)."""

    def __init__(self, websocket: WebSocket, server: WsServer):
        self.id = uuid.uuid4().hex
        self.websocket = websocket
        self.server = server
        self.rooms: set[str] = set()
        self.data: dict[str, Any] = {}

    @property
    def headers(self) -> Any:
        return self.websocket.headers

    @property
    def query_params(self) -> Any:
        return self.websocket.query_params

    @property
    def connected(self) -> bool:
        return self.websocket.client_state == WebSocketState.CONNECTED

    async def send(self, event: str, data: Any = None, *, id: str | int | None = None) -> None:  # noqa: A002
        if not self.connected:
            return
        message: dict[str, Any] = {"event": event, "data": jsonable_encoder(data)}
        if id is not None:
            message["id"] = id
        await self.websocket.send_text(json.dumps(message))

    async def join(self, room: str) -> None:
        self.rooms.add(room)
        self.server._rooms[room].add(self)  # noqa: SLF001

    async def leave(self, room: str) -> None:
        self.rooms.discard(room)
        self.server._rooms[room].discard(self)  # noqa: SLF001

    async def close(self, code: int = 1000) -> None:
        if self.connected:
            await self.websocket.close(code)


class _Room:
    def __init__(self, server: WsServer, rooms: tuple[str, ...]):
        self._server, self._rooms = server, rooms

    def to(self, room: str) -> _Room:
        return _Room(self._server, (*self._rooms, room))

    async def emit(self, event: str, data: Any = None) -> None:
        targets = {c for r in self._rooms for c in self._server._rooms.get(r, set())}  # noqa: SLF001
        for client in targets:
            await client.send(event, data)


class WsServer:
    """Broadcasting for one gateway: ``await self.server.emit("news", data)`` reaches everyone,
    ``self.server.to("room").emit(...)`` just a room. Set on the gateway instance as ``server``."""

    def __init__(self) -> None:
        self.clients: dict[str, WsClient] = {}
        self._rooms: dict[str, set[WsClient]] = defaultdict(set)

    def _add(self, client: WsClient) -> None:
        self.clients[client.id] = client

    def _remove(self, client: WsClient) -> None:
        self.clients.pop(client.id, None)
        for room in list(client.rooms):
            client.rooms.discard(room)
            self._rooms[room].discard(client)

    def to(self, room: str) -> _Room:
        return _Room(self, (room,))

    async def emit(self, event: str, data: Any = None) -> None:
        for client in list(self.clients.values()):
            await client.send(event, data)


class WsArgumentsHost:
    def __init__(self, client: WsClient, data: Any):
        self._client, self._data = client, data

    def get_client(self) -> WsClient:
        return self._client

    def get_data(self) -> Any:
        return self._data


class WsExecutionContext(ExecutionContext):
    """The context guards and interceptors get for a gateway message: ``get_type()`` is ``"ws"`` and
    ``switch_to_ws()`` gives the client and the message data. ``get_request()`` is the upgrade request's
    connection (headers, query string, cookies)."""

    def __init__(self, client: WsClient, data: Any, gateway_class: type, handler: Callable[..., Any]):
        super().__init__(client.websocket, gateway_class, handler)  # type: ignore[arg-type]
        self._ws = WsArgumentsHost(client, data)

    def get_type(self) -> str:
        return "ws"

    def switch_to_ws(self) -> WsArgumentsHost:
        return self._ws

    def switch_to_http(self) -> ExecutionContext:
        raise NotImplementedError("This is a WebSocket execution context: use switch_to_ws().")
