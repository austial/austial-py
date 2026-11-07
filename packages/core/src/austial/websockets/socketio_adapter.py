"""Socket.IO adapter -- serve ``@WebSocketGateway`` classes with the Socket.IO protocol (rooms, acknowledgements,
automatic reconnection, browser ``socket.io-client``), mirroring Nest's default ``IoAdapter``.
Needs ``pip install 'austial-core[socketio]'``.

::

    @Module(imports=[WebSocketsModule.for_root(adapter=SocketIoAdapter(cors_allowed_origins="https://app.example.com"))],
            providers=[ChatGateway])
    class ChatModule: ...

* The Socket.IO engine is mounted at ``/socket.io`` (the client's default ``path``).
* A gateway's ``path`` is its Socket.IO **namespace**: ``@WebSocketGateway("/chat")`` is ``io("https://host/chat")``.
* The gateway code is the same as for plain WebSockets. A handler's return value becomes the **acknowledgement**
  (when the client asked for one); ``WsResponse(event, data)`` and ``await client.send(...)`` emit events.
  ``handle_connection(client)``
  may reject a connection by raising ``WsException``/``ConnectionRefusedError`` or calling ``await client.close()``.
* ``client.join/leave`` and ``server.to(room).emit`` map to Socket.IO rooms.
"""

from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from starlette.requests import HTTPConnection

from austial.websockets.adapter import WsAdapter
from austial.websockets.types import WsClient, WsServer, _Room


class SocketIoClient(WsClient):
    """A Socket.IO connection exposed through the same surface as a plain WebSocket client."""

    def __init__(self, sio: Any, sid: str, namespace: str, environ: dict[str, Any], server: SocketIoServer):
        self.id = sid
        self._sio, self.namespace = sio, namespace
        self.server = server
        self.rooms = set()
        self.data = {}
        # The upgrade request's ASGI scope gives headers / query string / cookies, as for a plain WebSocket.
        self.websocket = HTTPConnection(environ.get("asgi.scope", {"type": "http", "headers": [], "query_string": b""}))  # type: ignore[assignment]
        self._connected = True

    @property
    def connected(self) -> bool:
        return self._connected

    async def send(self, event: str, data: Any = None, *, id: str | int | None = None) -> None:  # noqa: A002
        if self._connected:
            await self._sio.emit(event, jsonable_encoder(data), to=self.id, namespace=self.namespace)

    async def join(self, room: str) -> None:
        self.rooms.add(room)
        await self._sio.enter_room(self.id, room, namespace=self.namespace)

    async def leave(self, room: str) -> None:
        self.rooms.discard(room)
        await self._sio.leave_room(self.id, room, namespace=self.namespace)

    async def close(self, code: int = 1000) -> None:
        if self._connected:
            self._connected = False
            await self._sio.disconnect(self.id, namespace=self.namespace)


class _SioRoom(_Room):
    def __init__(self, server: SocketIoServer, rooms: tuple[str, ...]):
        self._sio_server, self._rooms_list = server, rooms

    def to(self, room: str) -> _SioRoom:
        return _SioRoom(self._sio_server, (*self._rooms_list, room))

    async def emit(self, event: str, data: Any = None) -> None:
        sio, namespace = self._sio_server.sio, self._sio_server.namespace
        for room in self._rooms_list:
            await sio.emit(event, jsonable_encoder(data), room=room, namespace=namespace)


class SocketIoServer(WsServer):
    def __init__(self, sio: Any, namespace: str):
        super().__init__()
        self.sio, self.namespace = sio, namespace

    def to(self, room: str) -> _SioRoom:
        return _SioRoom(self, (room,))

    async def emit(self, event: str, data: Any = None) -> None:
        await self.sio.emit(event, jsonable_encoder(data), namespace=self.namespace)


class SocketIoAdapter(WsAdapter):
    def __init__(self, *, cors_allowed_origins: str | list[str] | None = None, **server_options: Any):
        """``server_options`` go to ``socketio.AsyncServer`` (``ping_interval``, ``logger``, ...)."""
        self.cors_allowed_origins = cors_allowed_origins
        self.server_options = server_options
        self._sio: Any = None

    def _server(self) -> Any:
        if self._sio is None:
            try:
                import socketio
            except ImportError as exc:
                raise RuntimeError(
                    "SocketIoAdapter needs python-socketio: pip install 'austial-core[socketio]'"
                ) from exc
            self._sio = socketio.AsyncServer(
                async_mode="asgi", cors_allowed_origins=self.cors_allowed_origins or [], **self.server_options
            )
        return self._sio

    def mount(self, runner: Any, app: Any, path: str, gateway: Any, handlers: dict[str, Any]) -> SocketIoServer:
        import socketio
        from starlette.routing import Mount

        sio = self._server()
        namespace = path
        server = SocketIoServer(sio, namespace)
        clients: dict[str, SocketIoClient] = {}

        async def on_connect(sid: str, environ: dict[str, Any], auth: Any = None) -> None:
            client = SocketIoClient(sio, sid, namespace, environ, server)
            client.data["auth"] = auth
            clients[sid] = client
            server._add(client)  # noqa: SLF001
            handle = getattr(gateway, "handle_connection", None)
            if callable(handle):
                result = handle(client)
                if hasattr(result, "__await__"):
                    await result
            if not client.connected:  # rejected inside handle_connection
                raise ConnectionRefusedError("connection rejected")

        async def on_disconnect(sid: str, *args: Any) -> None:
            client = clients.pop(sid, None)
            if client is None:
                return
            client._connected = False  # noqa: SLF001
            server._remove(client)  # noqa: SLF001
            handle = getattr(gateway, "handle_disconnect", None)
            if callable(handle):
                result = handle(client)
                if hasattr(result, "__await__"):
                    await result

        sio.on("connect", on_connect, namespace=namespace)
        sio.on("disconnect", on_disconnect, namespace=namespace)

        for event, handler in handlers.items():

            async def on_event(sid: str, data: Any = None, *, event: str = event, handler: Any = handler) -> Any:
                client = clients[sid]
                reply = await runner.process(gateway, handler, client, event, data)
                if reply is None:
                    return None
                reply_event, payload = reply
                if reply_event == event:
                    return jsonable_encoder(payload)  # becomes the acknowledgement
                await client.send(reply_event, payload)  # WsResponse / exception events are emitted
                return None

            sio.on(event, on_event, namespace=namespace)

        if not any(getattr(route, "path", None) == "/socket.io" for route in app.router.routes):
            app.router.routes.append(Mount("/socket.io", app=socketio.ASGIApp(sio, socketio_path="socket.io")))
        return server
