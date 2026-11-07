"""Live-broker tests: the microservice transports and the Mongo ODM against real servers.

Skipped unless the matching environment variable points at a server (CI's ``brokers`` job starts them as service
containers; locally: ``AUSTIAL_TEST_REDIS_URL=redis://localhost:6379 pytest integration/brokers_spec.py``).

* ``AUSTIAL_TEST_REDIS_URL``     Redis Pub/Sub and Redis Streams
* ``AUSTIAL_TEST_NATS_URL``      NATS (``nats://localhost:4222``)
* ``AUSTIAL_TEST_RABBITMQ_URL``  RabbitMQ (``amqp://guest:guest@localhost/``)
* ``AUSTIAL_TEST_MONGO_URL``     MongoDB (``mongodb://localhost:27017``)
* ``AUSTIAL_TEST_MQTT_URL``      MQTT 5 broker (``localhost:1883``)
* ``AUSTIAL_TEST_KAFKA_URL``     Kafka bootstrap server (``localhost:9092``)

Locally: ``docker compose -f docker-compose.brokers.yml up -d --wait && source integration/env.sh``.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from austial import Controller, Module
from austial.microservices import (
    ClientOptions,
    ClientProxy,
    EventPattern,
    MessagePattern,
    MicroserviceOptions,
    Payload,
    RpcError,
    RpcException,
    Transport,
    create_microservice,
)

EVENTS: list[dict] = []


@Controller()
class Handlers:
    @MessagePattern("sum")
    def total(self, numbers: list = Payload()):
        return sum(numbers)

    @MessagePattern("fail")
    def fail(self):
        raise RpcException({"status": "error", "message": "bad", "code": 7})

    @EventPattern("thing.happened")
    def happened(self, payload: dict = Payload()):
        EVENTS.append(payload)


@Module(controllers=[Handlers])
class App:
    pass


async def round_trip(transport: Transport, url: str) -> None:
    prefix = f"it-{uuid.uuid4().hex[:8]}"  # isolates this run on a shared broker
    EVENTS.clear()
    server = create_microservice(App, MicroserviceOptions(transport, url=url, prefix=prefix, group=prefix))
    await server.listen()
    client = ClientProxy(ClientOptions("IT", transport, url=url, prefix=prefix, timeout=10))
    await client.connect()
    try:
        assert await client.send("sum", [1, 2, 3]) == 6
        assert await asyncio.gather(*(client.send("sum", [n, n]) for n in range(5))) == [0, 2, 4, 6, 8]
        with pytest.raises(RpcError) as caught:
            await client.send("fail")
        assert caught.value.payload["code"] == 7
        await client.emit("thing.happened", {"id": 1})
        for _ in range(100):
            if EVENTS:
                break
            await asyncio.sleep(0.05)
        assert EVENTS == [{"id": 1}]
    finally:
        await client.close()
        await server.close()


def _url(variable: str) -> str:
    url = os.environ.get(variable)
    if not url:
        pytest.skip(f"{variable} is not set")
    return url


async def test_redis_pubsub_live() -> None:
    await round_trip(Transport.REDIS, _url("AUSTIAL_TEST_REDIS_URL"))


async def test_redis_streams_live() -> None:
    await round_trip(Transport.REDIS_STREAMS, _url("AUSTIAL_TEST_REDIS_URL"))


async def test_nats_live() -> None:
    await round_trip(Transport.NATS, _url("AUSTIAL_TEST_NATS_URL"))


async def test_rabbitmq_live() -> None:
    await round_trip(Transport.RMQ, _url("AUSTIAL_TEST_RABBITMQ_URL"))


async def test_mongo_odm_live() -> None:
    from austial import AustialFactory, Injectable
    from austial.mongo import Document, Index, InjectModel, Model, MongoModule, Schema

    collection = f"it_{uuid.uuid4().hex[:8]}"

    @Schema(collection=collection, indexes=[Index("name", unique=True)])
    class Item(Document):
        name: str

    @Injectable()
    class Items:
        def __init__(self, items: Model[Item] = InjectModel(Item)):
            self.items = items

    @Module(
        imports=[
            MongoModule.for_root(uri=_url("AUSTIAL_TEST_MONGO_URL"), database="austial_it"),
            MongoModule.for_feature([Item]),
        ],
        providers=[Items],
    )
    class Root:
        pass

    app = AustialFactory.create(Root)
    await app.init()
    try:
        items = app.get(Items).items
        created = await items.create({"name": "a"})
        assert (await items.find_by_id(created.id)).name == "a"
        with pytest.raises(Exception, match="duplicate|E11000"):  # the unique index really exists
            await items.create({"name": "a"})
        assert await items.delete_many() == 1
    finally:
        await app.close()


async def test_mqtt_live() -> None:
    await round_trip(Transport.MQTT, _url("AUSTIAL_TEST_MQTT_URL"))


async def test_kafka_live() -> None:
    await round_trip(Transport.KAFKA, _url("AUSTIAL_TEST_KAFKA_URL"))


async def shared_group(transport: Transport, url: str) -> None:
    """Two replicas in one group: every request is handled exactly once, by one of them."""
    prefix = f"it-{uuid.uuid4().hex[:8]}"
    handled: list[str] = []

    def replica(name: str):
        @Controller()
        class Counter:
            @MessagePattern("count")
            def count(self, n: int = Payload()):
                handled.append(name)
                return n

        @Module(controllers=[Counter])
        class Mod:
            pass

        return create_microservice(Mod, MicroserviceOptions(transport, url=url, prefix=prefix, group=prefix))

    first, second = replica("a"), replica("b")
    await first.listen()
    await second.listen()
    await asyncio.sleep(1)  # let group membership settle (Kafka rebalances)
    client = ClientProxy(ClientOptions("IT", transport, url=url, prefix=prefix, timeout=15))
    await client.connect()
    try:
        assert await asyncio.gather(*(client.send("count", n) for n in range(20))) == list(range(20))
        assert len(handled) == 20, f"expected each request handled once, got {len(handled)} ({set(handled)})"
    finally:
        await client.close()
        await first.close()
        await second.close()


@pytest.mark.parametrize(
    ("transport", "variable"),
    [
        (Transport.REDIS_STREAMS, "AUSTIAL_TEST_REDIS_URL"),
        (Transport.NATS, "AUSTIAL_TEST_NATS_URL"),
        (Transport.RMQ, "AUSTIAL_TEST_RABBITMQ_URL"),
        (Transport.MQTT, "AUSTIAL_TEST_MQTT_URL"),
        (Transport.KAFKA, "AUSTIAL_TEST_KAFKA_URL"),
    ],
)
async def test_replicas_in_a_group_share_requests_live(transport: Transport, variable: str) -> None:
    await shared_group(transport, _url(variable))
