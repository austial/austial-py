"""Redis Streams transport -- Redis with consumer groups, so replicas share the load and messages survive a restart.

Pub/Sub (``Transport.REDIS``) broadcasts to every replica and drops messages nobody is listening for. Streams
(``Transport.REDIS_STREAMS``) append each message to a stream per pattern; replicas sharing ``group`` form a consumer
group (each message goes to one replica, acknowledged after the handler finishes) and a request published while no
replica is up is delivered when one starts. Each client reads replies from its own stream through a private consumer
group. Streams are capped (``maxlen``, approximate trimming).
Needs ``redis`` (``pip install 'austial-microservices[redis]'``).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Callable
from typing import Any

from austial.common.logger import Logger
from austial.microservices.transports.pubsub import Callback, PubSubBackend

_logger = Logger("RedisStreams")


class RedisStreamsBackend(PubSubBackend):
    def __init__(
        self,
        url: str = "redis://localhost:6379",
        *,
        client_factory: Callable[[], Any] | None = None,
        maxlen: int = 10_000,
        block_ms: int = 500,
    ):
        self.url, self._factory, self.maxlen, self.block_ms = url, client_factory, maxlen, block_ms
        self._client: Any = None
        self._tasks: list[asyncio.Task[None]] = []
        self._consumer = f"c-{uuid.uuid4().hex[:12]}"

    async def connect(self) -> None:
        if self._client is not None:
            return
        if self._factory is not None:
            self._client = self._factory()
            return
        try:
            from redis.asyncio import Redis
        except ImportError as exc:
            raise RuntimeError("The Redis transport needs redis: pip install 'austial-microservices[redis]'") from exc
        self._client = Redis.from_url(self.url)

    async def publish(self, topic: str, payload: bytes) -> None:
        await self._client.xadd(topic, {"d": payload}, maxlen=self.maxlen, approximate=True)

    async def subscribe(self, topic: str, callback: Callback, *, shared_group: str | None = None) -> None:
        # No shared group means a private one (reply streams): created at "$" so nothing published later is missed.
        group = shared_group or f"private-{uuid.uuid4().hex[:12]}"
        try:
            await self._client.xgroup_create(topic, group, id="$" if not shared_group else "0", mkstream=True)
        except Exception as exc:  # noqa: BLE001 - BUSYGROUP: another replica created it first
            if "BUSYGROUP" not in str(exc):
                raise
        self._tasks.append(asyncio.create_task(self._read(topic, group, callback)))

    async def _read(self, topic: str, group: str, callback: Callback) -> None:
        while True:
            try:
                batch = await self._client.xreadgroup(
                    group, self._consumer, {topic: ">"}, count=16, block=self.block_ms
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - broker hiccup: log and retry rather than die silently
                _logger.error(f"Reading '{topic}' failed: {type(exc).__name__}: {exc}")
                await asyncio.sleep(1)
                continue
            for _stream, entries in batch or []:
                for entry_id, fields in entries:
                    raw = fields.get(b"d", fields.get("d"))
                    if raw is not None:
                        await callback(raw if isinstance(raw, bytes) else str(raw).encode())
                    await self._client.xack(topic, group, entry_id)  # after the handler: a crash redelivers
            if not batch:
                await asyncio.sleep(0.01)

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        if self._client is not None:
            await self._client.aclose()
            self._client = None
