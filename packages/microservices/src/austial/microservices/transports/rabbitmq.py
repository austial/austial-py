"""RabbitMQ transport (queues on the default exchange).

Needs ``aio-pika`` (``pip install 'austial-microservices[rabbitmq]'``).

Each pattern is a queue; replicas consuming the same queue share the load (work-queue semantics). Per-client reply
queues are exclusive and deleted when the client disconnects.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from austial.microservices.transports.pubsub import Callback, PubSubBackend


class RabbitMqBackend(PubSubBackend):
    def __init__(self, url: str = "amqp://guest:guest@localhost/", *, connect: Callable[..., Any] | None = None):
        self.url, self._connect = url, connect
        self._connection: Any = None
        self._channel: Any = None
        self._aio_pika: Any = None

    async def connect(self) -> None:
        if self._connection is not None:
            return
        connect = self._connect
        if connect is None:
            try:
                import aio_pika
            except ImportError as exc:
                raise RuntimeError(
                    "The RabbitMQ transport needs aio-pika: pip install 'austial-microservices[rabbitmq]'"
                ) from exc
            self._aio_pika = aio_pika
            connect = aio_pika.connect_robust
        self._connection = await connect(self.url)
        self._channel = await self._connection.channel()

    def _message(self, payload: bytes) -> Any:
        if self._aio_pika is not None:
            return self._aio_pika.Message(body=payload)
        return payload  # test doubles take the bytes directly

    async def publish(self, topic: str, payload: bytes) -> None:
        await self._channel.default_exchange.publish(self._message(payload), routing_key=topic)

    async def subscribe(self, topic: str, callback: Callback, *, shared_group: str | None = None) -> None:
        is_reply = ".reply." in topic
        queue = await self._channel.declare_queue(topic, exclusive=is_reply, auto_delete=is_reply, durable=not is_reply)

        async def on_message(message: Any) -> None:
            async with message.process():
                await callback(message.body)

        await queue.consume(on_message)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = self._channel = None
