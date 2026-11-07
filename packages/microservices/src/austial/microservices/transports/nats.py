"""NATS transport. Needs ``nats-py`` (``pip install 'austial-microservices[nats]'``).

Replicas that share a ``group`` form a NATS *queue group*: each request goes to one of them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from austial.microservices.transports.pubsub import Callback, PubSubBackend


class NatsBackend(PubSubBackend):
    def __init__(
        self, url: str = "nats://localhost:4222", *, connect: Callable[..., Any] | None = None, **options: Any
    ):
        self.url, self._connect, self._options = url, connect, options
        self._nc: Any = None

    async def connect(self) -> None:
        if self._nc is not None:
            return
        connect = self._connect
        if connect is None:
            try:
                import nats
            except ImportError as exc:
                raise RuntimeError(
                    "The NATS transport needs nats-py: pip install 'austial-microservices[nats]'"
                ) from exc
            connect = nats.connect
        self._nc = await connect(self.url, **self._options)

    async def publish(self, topic: str, payload: bytes) -> None:
        await self._nc.publish(topic, payload)
        await self._nc.flush()

    async def subscribe(self, topic: str, callback: Callback, *, shared_group: str | None = None) -> None:
        async def on_message(message: Any) -> None:
            await callback(message.data)

        await self._nc.subscribe(topic, queue=shared_group or "", cb=on_message)

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None
