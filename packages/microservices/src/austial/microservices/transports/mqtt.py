"""MQTT transport. Needs ``aiomqtt`` (``pip install 'austial-microservices[mqtt]'``).

Replicas sharing a ``group`` use MQTT 5 *shared subscriptions* (``$share/<group>/<topic>``), so each message reaches
one of them (the broker must support them, e.g. Mosquitto 2, EMQX, HiveMQ).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from austial.microservices.transports.pubsub import Callback, PubSubBackend


class MqttBackend(PubSubBackend):
    def __init__(self, host: str = "localhost", port: int = 1883, *, client_factory: Any = None, **options: Any):
        self.host, self.port, self._options, self._factory = host, port, options, client_factory
        self._client: Any = None
        self._callbacks: dict[str, Callback] = {}
        self._reader: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        factory = self._factory
        if factory is None:
            try:
                import aiomqtt
            except ImportError as exc:
                raise RuntimeError(
                    "The MQTT transport needs aiomqtt: pip install 'austial-microservices[mqtt]'"
                ) from exc
            factory = aiomqtt.Client
        self._client = factory(hostname=self.host, port=self.port, **self._options)
        await self._client.__aenter__()

    async def publish(self, topic: str, payload: bytes) -> None:
        await self._client.publish(topic, payload)

    async def subscribe(self, topic: str, callback: Callback, *, shared_group: str | None = None) -> None:
        self._callbacks[topic] = callback
        await self._client.subscribe(f"$share/{shared_group}/{topic}" if shared_group else topic)
        if self._reader is None:
            self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        async for message in self._client.messages:
            callback = self._callbacks.get(str(message.topic))
            if callback is not None:
                await callback(bytes(message.payload))

    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
            self._reader = None
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None
