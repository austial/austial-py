"""Transports: how microservice messages travel.

Built in: ``TCP`` (JSON lines over asyncio streams), ``LOCAL`` (in-process, for tests and modular monoliths), and the
broker transports ``REDIS``, ``NATS``, ``KAFKA``, ``MQTT``, ``RMQ`` (RabbitMQ) and ``GRPC``
(see ``austial.microservices.transports``).
Anything else: implement :class:`ServerTransport` and :class:`ClientTransport` (small ABCs below) and pass
``Transport.CUSTOM`` with ``custom_server`` / ``custom_client``.
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
import itertools
import json
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


class Transport(enum.Enum):
    TCP = "tcp"
    LOCAL = "local"
    REDIS = "redis"  # Pub/Sub: every replica receives every message
    REDIS_STREAMS = "redis_streams"  # consumer groups: load-balanced, acknowledged
    NATS = "nats"
    KAFKA = "kafka"
    MQTT = "mqtt"
    RMQ = "rmq"  # RabbitMQ
    GRPC = "grpc"
    CUSTOM = "custom"


class RpcError(Exception):
    """Raised on the client when the remote handler failed; ``payload`` is what the server sent."""

    def __init__(self, payload: Any):
        self.payload = payload
        message = payload.get("message") if isinstance(payload, dict) else payload
        super().__init__(str(message))


class RpcException(Exception):
    """Raise from a handler to send a structured error to the caller."""

    def __init__(self, message: str | dict):
        self.payload = message if isinstance(message, dict) else {"status": "error", "message": message}
        super().__init__(str(message))


def pattern_key(pattern: Any) -> str:
    """A stable key for a pattern: a string is itself; a dict is its sorted JSON (``{"cmd": "sum"}``)."""
    return pattern if isinstance(pattern, str) else json.dumps(pattern, sort_keys=True)


# A server hands each incoming (kind, pattern_key, data) to this and gets the response back.
ServerHandler = Callable[[str, str, Any], Awaitable[Any]]


class ServerTransport(ABC):
    patterns: dict[str, list[str]] = {}  # {"request": [...], "event": [...]}: set before listen() for broker transports

    @abstractmethod
    async def listen(self, handler: ServerHandler) -> None:
        """Start accepting messages; return once ready."""

    @abstractmethod
    async def close(self) -> None: ...


class ClientTransport(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def request(self, pattern: str, data: Any) -> Any:
        """Send and wait for the response; raise :class:`RpcError` if the handler failed."""

    @abstractmethod
    async def emit(self, pattern: str, data: Any) -> None:
        """Fire and forget."""

    @abstractmethod
    async def close(self) -> None: ...


@dataclass
class MicroserviceOptions:
    transport: Transport = Transport.TCP
    host: str = "127.0.0.1"
    port: int = 3001
    name: str = "default"  # LOCAL transport: the broker name clients connect to
    url: str | None = None  # broker URL: redis://..., nats://..., amqp://..., kafka bootstrap "host:port", mqtt host
    group: str = "austial"  # consumer/queue group: replicas sharing it share the load (Kafka, NATS, MQTT shared subs)
    prefix: str = ""  # prepended to every topic, to keep several environments apart on one broker
    extra: dict[str, Any] = field(default_factory=dict)  # passed to the broker client (credentials, TLS, ...)
    codec: Any = None  # broker transports: object with encode(dict) -> bytes / decode(bytes) -> dict (default JSON)
    custom_server: ServerTransport | None = None


@dataclass
class ClientOptions:
    name: str
    transport: Transport = Transport.TCP
    host: str = "127.0.0.1"
    port: int = 3001
    broker: str = "default"  # LOCAL transport: which in-process server to talk to
    url: str | None = None
    prefix: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    codec: Any = None
    custom_client: ClientTransport | None = None
    timeout: float = 5.0


# -- LOCAL ---------------------------------------------------------------------------------

_local_servers: dict[str, ServerHandler] = {}


class LocalServer(ServerTransport):
    def __init__(self, name: str):
        self.name = name

    async def listen(self, handler: ServerHandler) -> None:
        _local_servers[self.name] = handler

    async def close(self) -> None:
        _local_servers.pop(self.name, None)


class LocalClient(ClientTransport):
    def __init__(self, broker: str):
        self.broker = broker

    async def connect(self) -> None:
        return None

    def _handler(self) -> ServerHandler:
        try:
            return _local_servers[self.broker]
        except KeyError:
            raise ConnectionError(f"No local microservice named '{self.broker}' is listening") from None

    async def request(self, pattern: str, data: Any) -> Any:
        return await self._handler()("request", pattern, data)

    async def emit(self, pattern: str, data: Any) -> None:
        await self._handler()("event", pattern, data)

    async def close(self) -> None:
        return None


# -- TCP (JSON lines) ----------------------------------------------------------------------


class TcpServer(ServerTransport):
    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self._server: asyncio.AbstractServer | None = None
        self._connections: set[asyncio.Task[None]] = set()

    async def listen(self, handler: ServerHandler) -> None:
        async def on_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            task = asyncio.current_task()
            if task is not None:
                self._connections.add(task)
            pending: set[asyncio.Task[None]] = set()

            async def serve(line: bytes) -> None:
                message = json.loads(line)
                if message["kind"] == "event":
                    # Events have no caller to report to; the handler registry already logs failures.
                    with contextlib.suppress(Exception):
                        await handler("event", message["pattern"], message.get("data"))
                    return
                try:
                    reply: dict[str, Any] = {
                        "id": message["id"],
                        "response": await handler("request", message["pattern"], message.get("data")),
                    }
                except RpcException as exc:
                    reply = {"id": message["id"], "err": exc.payload}
                except Exception as exc:  # noqa: BLE001
                    reply = {"id": message["id"], "err": {"status": "error", "message": f"{type(exc).__name__}: {exc}"}}
                writer.write((json.dumps(reply, default=str) + "\n").encode())
                await writer.drain()

            try:
                while line := await reader.readline():
                    work = asyncio.create_task(serve(line))
                    pending.add(work)
                    work.add_done_callback(pending.discard)
            except (ConnectionResetError, asyncio.IncompleteReadError):
                pass
            finally:
                for work in list(pending):
                    work.cancel()
                writer.close()
                if task is not None:
                    self._connections.discard(task)

        self._server = await asyncio.start_server(on_connection, self.host, self.port)
        if self.port == 0:
            self.port = self._server.sockets[0].getsockname()[1]

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            for task in list(self._connections):
                task.cancel()
            await self._server.wait_closed()
            self._server = None


class TcpClient(ClientTransport):
    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host, self.port, self.timeout = host, port, timeout
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._ids = itertools.count(1)

    async def connect(self) -> None:
        if self._writer is not None:
            return
        reader, self._writer = await asyncio.open_connection(self.host, self.port)

        async def read_loop() -> None:
            while line := await reader.readline():
                reply = json.loads(line)
                future = self._pending.pop(reply["id"], None)
                if future is None or future.done():
                    continue
                if "err" in reply:
                    future.set_exception(RpcError(reply["err"]))
                else:
                    future.set_result(reply.get("response"))
            for future in self._pending.values():  # connection closed with calls in flight
                if not future.done():
                    future.set_exception(ConnectionError("The microservice closed the connection"))
            self._pending.clear()

        self._reader_task = asyncio.create_task(read_loop())

    async def _send(self, message: dict[str, Any]) -> None:
        if self._writer is None:
            await self.connect()
        assert self._writer is not None
        self._writer.write((json.dumps(message, default=str) + "\n").encode())
        await self._writer.drain()

    async def request(self, pattern: str, data: Any) -> Any:
        await self.connect()
        message_id = next(self._ids)
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[message_id] = future
        try:
            await self._send({"id": message_id, "kind": "request", "pattern": pattern, "data": data})
            return await asyncio.wait_for(future, self.timeout)
        finally:
            self._pending.pop(message_id, None)

    async def emit(self, pattern: str, data: Any) -> None:
        await self._send({"kind": "event", "pattern": pattern, "data": data})

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
        if self._writer is not None:
            self._writer.close()
        self._writer = None
        self._reader_task = None
