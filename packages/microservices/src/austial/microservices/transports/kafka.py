"""Kafka transport. Needs ``aiokafka`` (``pip install 'austial-microservices[kafka]'``).

Servers join a consumer group (``group``), so replicas share the partitions of a request topic. Topics must exist or the
broker must auto-create them (``auto.create.topics.enable``); reply topics are per client and created on first use.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from austial.microservices.transports.pubsub import Callback, PubSubBackend


class KafkaBackend(PubSubBackend):
    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        *,
        group: str = "austial",
        producer_factory: Any = None,
        consumer_factory: Any = None,
        **options: Any,
    ):
        self.bootstrap_servers, self.group, self._options = bootstrap_servers, group, options
        self._producer_factory, self._consumer_factory = producer_factory, consumer_factory
        self._producer: Any = None
        self._consumers: list[tuple[Any, asyncio.Task[None]]] = []

    def _classes(self) -> tuple[Any, Any]:
        if self._producer_factory and self._consumer_factory:
            return self._producer_factory, self._consumer_factory
        try:
            from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
        except ImportError as exc:
            raise RuntimeError(
                "The Kafka transport needs aiokafka: pip install 'austial-microservices[kafka]'"
            ) from exc
        return AIOKafkaProducer, AIOKafkaConsumer

    async def connect(self) -> None:
        if self._producer is None:
            producer_cls, _ = self._classes()
            self._producer = producer_cls(bootstrap_servers=self.bootstrap_servers, **self._options)
            await self._producer.start()

    async def publish(self, topic: str, payload: bytes) -> None:
        await self._producer.send_and_wait(topic, payload)

    async def subscribe(self, topic: str, callback: Callback, *, shared_group: str | None = None) -> None:
        _, consumer_cls = self._classes()
        consumer = consumer_cls(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=shared_group or f"{self.group}-{topic}-{id(callback)}",  # reply topics: a private group each
            auto_offset_reset="latest",
            **self._options,
        )
        await consumer.start()

        async def pump() -> None:
            async for record in consumer:
                await callback(record.value)

        self._consumers.append((consumer, asyncio.create_task(pump())))

    async def close(self) -> None:
        for consumer, task in self._consumers:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await consumer.stop()
        self._consumers.clear()
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
