"""Redis transport (Pub/Sub). Needs ``redis`` (``pip install 'austial-microservices[redis]'``).

Redis Pub/Sub broadcasts: *every* running instance of the microservice receives each message, so run one instance per
pattern set, or put a single consumer behind it. (Load-balanced consumption needs Redis Streams, not provided here.)
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import Any

from austial.microservices.transports.pubsub import Callback, PubSubBackend


class RedisBackend(PubSubBackend):
    def __init__(self, url: str = "redis://localhost:6379", *, client_factory: Callable[[], Any] | None = None):
        self.url, self._factory = url, client_factory
        self._client: Any = None
        self._pubsub: Any = None
        self._callbacks: dict[str, Callback] = {}
        self._reader: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        if self._factory is not None:
            self._client = self._factory()
        else:
            try:
                from redis.asyncio import Redis
            except ImportError as exc:
                raise RuntimeError(
                    "The Redis transport needs redis: pip install 'austial-microservices[redis]'"
                ) from exc
            self._client = Redis.from_url(self.url)
        self._pubsub = self._client.pubsub()

    async def publish(self, topic: str, payload: bytes) -> None:
        await self._client.publish(topic, payload)

    async def subscribe(self, topic: str, callback: Callback, *, shared_group: str | None = None) -> None:
        self._callbacks[topic] = callback
        await self._pubsub.subscribe(topic)
        if self._reader is None:
            self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        while True:
            message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if message is None:
                await asyncio.sleep(0.01)
                continue
            channel = message["channel"]
            channel = channel.decode() if isinstance(channel, bytes) else channel
            callback = self._callbacks.get(channel)
            if callback is not None:
                data = message["data"]
                await callback(data if isinstance(data, bytes) else str(data).encode())

    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
            self._reader = None
        if self._pubsub is not None:
            await self._pubsub.aclose()
        if self._client is not None:
            await self._client.aclose()
        self._client = self._pubsub = None
