"""One request-reply protocol over any publish/subscribe broker (Redis, NATS, Kafka, MQTT, RabbitMQ).

Wire format (JSON):

* a **request** is published to the pattern's topic:
  ``{"id": "...", "data": ..., "reply_to": "<topic>.reply.<client>"}``
* an **event** is published to the same topic without ``id``: ``{"data": ...}``
* the server answers a request by publishing ``{"id": "...", "response": ...}`` or ``{"id": "...", "err": {...}}`` to
  the request's ``reply_to`` topic (one per client, so clients never see each other's replies).

Each broker only has to provide :class:`PubSubBackend`: connect, publish bytes to a topic, subscribe a callback to a
topic, close. Everything above that is shared here, so the protocol behaves identically on every broker.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from austial.common.logger import Logger
from austial.microservices.transport import (
    ClientTransport,
    RpcError,
    RpcException,
    ServerHandler,
    ServerTransport,
)

_logger = Logger("PubSubTransport")

Callback = Callable[[bytes], Awaitable[None]]


def topic_for(pattern_key: str, prefix: str = "") -> str:
    """A broker-safe topic for a pattern key. Plain dotted names are kept; dict patterns (JSON) and anything with
    characters brokers dislike are replaced by a short hash, identically on client and server."""
    if pattern_key and all(c.isalnum() or c in "._-" for c in pattern_key):
        return f"{prefix}{pattern_key}"
    return f"{prefix}p_{hashlib.sha1(pattern_key.encode()).hexdigest()[:16]}"  # noqa: S324 - a name, not security


class JsonCodec:
    """The default wire encoding. Any object with ``encode(dict) -> bytes`` and ``decode(bytes) -> dict`` can replace it
    (``codec=`` on the options): msgpack, a schema registry, a compressing or encrypting wrapper..."""

    def encode(self, message: dict[str, Any]) -> bytes:
        return json.dumps(message, default=str).encode()

    def decode(self, raw: bytes) -> dict[str, Any]:
        decoded: dict[str, Any] = json.loads(raw)
        return decoded


class PubSubBackend(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def publish(self, topic: str, payload: bytes) -> None: ...

    @abstractmethod
    async def subscribe(self, topic: str, callback: Callback, *, shared_group: str | None = None) -> None:
        """Deliver every message on ``topic`` to ``callback``. With ``shared_group``, replicas that subscribe with the
        same group share the load (each message goes to one of them) where the broker supports it."""

    @abstractmethod
    async def close(self) -> None: ...


class PubSubServer(ServerTransport):
    def __init__(self, backend: PubSubBackend, *, prefix: str = "", group: str | None = None, codec: Any = None):
        self.codec = codec or JsonCodec()
        self.backend, self.prefix, self.group = backend, prefix, group
        self.patterns: dict[str, list[str]] = {"request": [], "event": []}  # set by MicroserviceServer before listen()
        self._handler: ServerHandler | None = None

    async def listen(self, handler: ServerHandler) -> None:
        self._handler = handler
        await self.backend.connect()
        for key in dict.fromkeys([*self.patterns["request"], *self.patterns["event"]]):
            await self.backend.subscribe(topic_for(key, self.prefix), self._on_message(key), shared_group=self.group)

    def _on_message(self, key: str) -> Callback:
        async def on_message(payload: bytes) -> None:
            assert self._handler is not None
            try:
                message = self.codec.decode(payload)
            except ValueError:
                _logger.warn(f"Dropping a non-JSON message on '{key}'")
                return
            if "id" not in message:  # an event: nobody to answer
                try:
                    await self._handler("event", key, message.get("data"))
                except Exception as exc:  # noqa: BLE001
                    _logger.error(f"Event handler for {key} raised {type(exc).__name__}: {exc}")
                return
            try:
                reply: dict[str, Any] = {
                    "id": message["id"],
                    "response": await self._handler("request", key, message.get("data")),
                }
            except RpcException as exc:
                reply = {"id": message["id"], "err": exc.payload}
            except Exception as exc:  # noqa: BLE001
                reply = {"id": message["id"], "err": {"status": "error", "message": f"{type(exc).__name__}: {exc}"}}
            if message.get("reply_to"):
                await self.backend.publish(message["reply_to"], self.codec.encode(reply))

        return on_message

    async def close(self) -> None:
        await self.backend.close()


class PubSubClient(ClientTransport):
    def __init__(self, backend: PubSubBackend, *, prefix: str = "", timeout: float = 5.0, codec: Any = None):
        self.codec = codec or JsonCodec()
        self.backend, self.prefix, self.timeout = backend, prefix, timeout
        self._client_id = uuid.uuid4().hex[:12]
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._subscribed: set[str] = set()
        self._lock = asyncio.Lock()
        self._connected = False

    async def connect(self) -> None:
        if not self._connected:
            await self.backend.connect()
            self._connected = True

    async def _reply_topic(self, topic: str) -> str:
        reply_topic = f"{topic}.reply.{self._client_id}"
        async with self._lock:  # subscribe exactly once, and before the request that needs the reply goes out
            if reply_topic not in self._subscribed:
                await self.backend.subscribe(reply_topic, self._on_reply)
                self._subscribed.add(reply_topic)
        return reply_topic

    async def _on_reply(self, payload: bytes) -> None:
        reply = self.codec.decode(payload)
        future = self._pending.pop(str(reply.get("id")), None)
        if future is None or future.done():
            return
        if "err" in reply:
            future.set_exception(RpcError(reply["err"]))
        else:
            future.set_result(reply.get("response"))

    async def request(self, pattern: str, data: Any) -> Any:
        await self.connect()
        topic = topic_for(pattern, self.prefix)
        reply_to = await self._reply_topic(topic)
        message_id = uuid.uuid4().hex
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[message_id] = future
        try:
            body = self.codec.encode({"id": message_id, "data": data, "reply_to": reply_to})
            await self.backend.publish(topic, body)
            return await asyncio.wait_for(future, self.timeout)
        finally:
            self._pending.pop(message_id, None)

    async def emit(self, pattern: str, data: Any) -> None:
        await self.connect()
        await self.backend.publish(topic_for(pattern, self.prefix), self.codec.encode({"data": data}))

    async def close(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
        await self.backend.close()
        self._connected = False
