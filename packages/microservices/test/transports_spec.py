"""The broker and gRPC transports.

* gRPC runs against the real ``grpcio`` library over localhost.
* Redis runs against the real ``redis`` client with ``fakeredis`` standing in for the server.
* NATS, Kafka, MQTT and RabbitMQ use in-memory fakes that mimic each library's async API. They exercise our
  adapters and the shared protocol, and ``test_adapters_only_call_api_that_exists_in_the_real_libraries`` checks the
  names and signatures we rely on against the installed libraries. No live broker is involved.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
from types import SimpleNamespace
from typing import Any

import fakeredis
import fakeredis.aioredis
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
from austial.microservices.transports import PubSubBackend, PubSubClient, PubSubServer, topic_for

EVENTS: list[Any] = []


@Controller()
class Handlers:
    @MessagePattern({"cmd": "sum"})
    def total(self, numbers: list[int] = Payload()) -> int:
        return sum(numbers)

    @MessagePattern("echo.text")
    async def echo(self, data):
        return data

    @MessagePattern("fail")
    def fail(self):
        raise RpcException({"status": "error", "message": "bad", "code": 7})

    @MessagePattern("bug")
    def bug(self):
        raise ZeroDivisionError("oops")

    @MessagePattern("slow")
    async def slow(self):
        await asyncio.sleep(2)

    @EventPattern("user.created")
    def created(self, user: dict = Payload()):
        EVENTS.append(user)


@Module(controllers=[Handlers])
class App:
    pass


async def eventually(condition, timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        assert asyncio.get_running_loop().time() < deadline, "condition never became true"
        await asyncio.sleep(0.01)


async def exercise(server_options: MicroserviceOptions, client_options: ClientOptions) -> None:
    """The same behaviour must hold on every transport."""
    EVENTS.clear()
    ms = create_microservice(App, server_options)
    await ms.listen()
    client = ClientProxy(client_options)
    await client.connect()
    try:
        assert await client.send({"cmd": "sum"}, [1, 2, 3]) == 6  # dict patterns work (hashed topics on brokers)
        assert await client.send("echo.text", {"nested": [1, None, "x"]}) == {"nested": [1, None, "x"]}
        results = await asyncio.gather(*(client.send({"cmd": "sum"}, [n, n]) for n in range(10)))
        assert results == [n * 2 for n in range(10)]  # concurrent calls get their own replies

        with pytest.raises(RpcError) as caught:
            await client.send("fail")
        assert caught.value.payload == {"status": "error", "message": "bad", "code": 7}
        with pytest.raises(RpcError, match="ZeroDivisionError"):
            await client.send("bug")
        with pytest.raises(asyncio.TimeoutError):
            await client.send("slow", timeout=0.1)

        await client.emit("user.created", {"id": 1})
        await client.emit("user.unknown", {"id": 2})  # nobody listens: dropped
        await eventually(lambda: EVENTS == [{"id": 1}])
    finally:
        await client.close()
        await ms.close()


# -- gRPC (real library) ---------------------------------------------------------------------


async def test_grpc_transport_against_the_real_library() -> None:
    server = MicroserviceOptions(Transport.GRPC, host="127.0.0.1", port=0)
    ms = create_microservice(App, server)
    await ms.listen()
    port = ms.server.transport.port  # type: ignore[attr-defined]  # the port gRPC actually bound
    assert port > 0
    client = ClientProxy(ClientOptions(name="G", transport=Transport.GRPC, host="127.0.0.1", port=port, timeout=2))
    EVENTS.clear()
    try:
        assert await client.send({"cmd": "sum"}, [4, 5]) == 9
        with pytest.raises(RpcError) as caught:
            await client.send("fail")
        assert caught.value.payload["code"] == 7
        with pytest.raises(RpcError, match="no matching message handler"):
            await client.send("nope")
        await client.emit("user.created", {"id": 9})
        await eventually(lambda: EVENTS == [{"id": 9}])
        assert (await asyncio.gather(*(client.send("echo.text", n) for n in range(8)))) == list(range(8))
    finally:
        await client.close()
        await ms.close()


async def test_grpc_call_deadline_surfaces_as_an_error() -> None:
    import grpc

    ms = create_microservice(App, MicroserviceOptions(Transport.GRPC, host="127.0.0.1", port=0))
    await ms.listen()
    port = ms.server.transport.port  # type: ignore[attr-defined]
    client = ClientProxy(ClientOptions(name="G", transport=Transport.GRPC, host="127.0.0.1", port=port, timeout=0.2))
    try:
        with pytest.raises((grpc.aio.AioRpcError, asyncio.TimeoutError)):
            await client.send("slow")
    finally:
        await client.close()
        await ms.close()


# -- Redis (real client, fake server) --------------------------------------------------------


async def test_redis_transport_with_the_real_client() -> None:
    fake_server = fakeredis.FakeServer()

    def factory():
        return fakeredis.aioredis.FakeRedis(server=fake_server)

    extra = {"client_factory": factory}
    await exercise(
        MicroserviceOptions(Transport.REDIS, extra=extra),
        ClientOptions(name="R", transport=Transport.REDIS, extra=extra, timeout=2),
    )


async def test_a_custom_codec_changes_the_wire_format_on_both_sides() -> None:
    import base64

    seen: list[bytes] = []

    class Base64Codec:
        def encode(self, message):
            raw = base64.b64encode(json.dumps(message).encode())
            seen.append(raw)
            return raw

        def decode(self, raw):
            return json.loads(base64.b64decode(raw))

    fake_server = fakeredis.FakeServer()
    extra = {"client_factory": lambda: fakeredis.aioredis.FakeRedis(server=fake_server)}
    await exercise(
        MicroserviceOptions(Transport.REDIS, extra=extra, codec=Base64Codec()),
        ClientOptions(name="C", transport=Transport.REDIS, extra=extra, codec=Base64Codec(), timeout=2),
    )
    assert seen and all(not chunk.startswith(b"{") for chunk in seen)  # nothing went out as plain JSON


async def test_redis_clients_have_private_reply_topics_and_prefixes_isolate_environments() -> None:
    fake_server = fakeredis.FakeServer()
    extra = {"client_factory": lambda: fakeredis.aioredis.FakeRedis(server=fake_server)}
    ms = create_microservice(App, MicroserviceOptions(Transport.REDIS, prefix="prod.", extra=extra))
    await ms.listen()
    one = ClientProxy(ClientOptions(name="1", transport=Transport.REDIS, prefix="prod.", extra=extra, timeout=2))
    two = ClientProxy(ClientOptions(name="2", transport=Transport.REDIS, prefix="prod.", extra=extra, timeout=2))
    staging = ClientProxy(
        ClientOptions(name="3", transport=Transport.REDIS, prefix="staging.", extra=extra, timeout=0.3)
    )
    try:
        a, b = await asyncio.gather(one.send("echo.text", "from-one"), two.send("echo.text", "from-two"))
        assert (a, b) == ("from-one", "from-two")  # each client got its own answer
        with pytest.raises(asyncio.TimeoutError):
            await staging.send("echo.text", "x")  # nobody serves the staging. prefix
    finally:
        for client in (one, two, staging):
            await client.close()
        await ms.close()


# -- in-memory fakes mimicking each library -------------------------------------------------


class Bus:
    """Routes published payloads to subscriber callbacks, by topic."""

    def __init__(self) -> None:
        self.subscribers: dict[str, list] = {}

    def subscribe(self, topic: str, deliver) -> None:
        self.subscribers.setdefault(topic, []).append(deliver)

    async def publish(self, topic: str, payload: bytes) -> None:
        for deliver in list(self.subscribers.get(topic, [])):
            asyncio.get_running_loop().create_task(deliver(payload))


# nats-py: `await nats.connect(url)` -> client with publish/flush/subscribe(queue=, cb=)/drain
def nats_fake(bus: Bus):
    class FakeNats:
        queues: list[str] = []

        async def publish(self, subject, payload):
            await bus.publish(subject, payload)

        async def flush(self):
            return None

        async def subscribe(self, subject, queue="", cb=None):
            FakeNats.queues.append(queue)

            async def deliver(payload):
                await cb(SimpleNamespace(data=payload))

            bus.subscribe(subject, deliver)

        async def drain(self):
            return None

    async def connect(url, **options):
        return FakeNats()

    return connect, FakeNats


# aiokafka: AIOKafkaProducer(bootstrap_servers).start()/send_and_wait(topic, value)/stop();
#           AIOKafkaConsumer(*topics, bootstrap_servers, group_id, ...).start()/stop() + async iteration of records
def kafka_fakes(bus: Bus):
    class FakeProducer:
        def __init__(self, bootstrap_servers, **options):
            self.bootstrap_servers = bootstrap_servers

        async def start(self):
            return None

        async def stop(self):
            return None

        async def send_and_wait(self, topic, value):
            await bus.publish(topic, value)

    class FakeConsumer:
        groups: list[str] = []

        def __init__(self, *topics, bootstrap_servers, group_id, auto_offset_reset, **options):
            self.queue: asyncio.Queue = asyncio.Queue()
            FakeConsumer.groups.append(group_id)
            for topic in topics:
                bus.subscribe(topic, self._deliver)

        async def _deliver(self, payload):
            await self.queue.put(SimpleNamespace(value=payload))

        async def start(self):
            return None

        async def stop(self):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.queue.get()

    return FakeProducer, FakeConsumer


# aiomqtt: Client(hostname=, port=) as async context manager; publish/subscribe; `messages` async iterator
def mqtt_fake(bus: Bus):
    class FakeMqtt:
        subscriptions: list[str] = []

        def __init__(self, hostname, port, **options):
            self.hostname, self.port = hostname, port
            self.queue: asyncio.Queue = asyncio.Queue()
            self.messages = self._messages()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def publish(self, topic, payload):
            await bus.publish(topic, payload)

        async def subscribe(self, topic):
            FakeMqtt.subscriptions.append(topic)
            real = topic.split("/", 2)[2] if topic.startswith("$share/") else topic

            async def deliver(payload, real=real):
                await self.queue.put(SimpleNamespace(topic=real, payload=payload))

            bus.subscribe(real, deliver)

        async def _messages(self):
            while True:
                yield await self.queue.get()

    return FakeMqtt


# aio-pika: `await connect(url)` -> connection.channel(); channel.declare_queue(...); queue.consume(cb);
#           channel.default_exchange.publish(message, routing_key=)
def rabbit_fake(bus: Bus):
    declared: list[dict] = []

    class Incoming:
        def __init__(self, body):
            self.body = body

        @contextlib.asynccontextmanager
        async def process(self):
            yield

    class Queue:
        def __init__(self, name):
            self.name = name

        async def consume(self, callback):
            async def deliver(payload):
                await callback(Incoming(payload))

            bus.subscribe(self.name, deliver)

    class Exchange:
        async def publish(self, message, routing_key):
            await bus.publish(routing_key, message)

    class Channel:
        default_exchange = Exchange()

        async def declare_queue(self, name, exclusive, auto_delete, durable):
            declared.append({"name": name, "exclusive": exclusive, "auto_delete": auto_delete, "durable": durable})
            return Queue(name)

    class Connection:
        async def channel(self):
            return Channel()

        async def close(self):
            return None

    async def connect(url):
        return Connection()

    return connect, declared


async def test_nats_transport_with_a_fake_client() -> None:
    connect, fake_cls = nats_fake(Bus())
    options = {"connect": connect}
    await exercise(
        MicroserviceOptions(Transport.NATS, group="workers", extra=options),
        ClientOptions(name="N", transport=Transport.NATS, extra=options, timeout=2),
    )
    assert "workers" in fake_cls.queues  # replicas of the service form one NATS queue group


async def test_kafka_transport_with_fake_clients() -> None:
    producer, consumer = kafka_fakes(Bus())
    options = {"producer_factory": producer, "consumer_factory": consumer}
    await exercise(
        MicroserviceOptions(Transport.KAFKA, group="math", url="broker:9092", extra=options),
        ClientOptions(name="K", transport=Transport.KAFKA, extra=options, timeout=2),
    )
    assert any(g.startswith("austial-") for g in consumer.groups)  # reply consumers never share a group


async def test_mqtt_transport_with_a_fake_client() -> None:
    client_cls = mqtt_fake(Bus())
    options = {"client_factory": client_cls}
    await exercise(
        MicroserviceOptions(Transport.MQTT, url="mqtt.internal:1884", group="math", extra=options),
        ClientOptions(name="M", transport=Transport.MQTT, url="mqtt.internal:1884", extra=options, timeout=2),
    )
    assert any(s.startswith("$share/math/") for s in client_cls.subscriptions)  # shared subscription for load balancing
    assert not any(s.startswith("$share/") and ".reply." in s for s in client_cls.subscriptions)


async def test_rabbitmq_transport_with_a_fake_connection() -> None:
    connect, declared = rabbit_fake(Bus())
    options = {"connect": connect}
    await exercise(
        MicroserviceOptions(Transport.RMQ, extra=options),
        ClientOptions(name="Q", transport=Transport.RMQ, extra=options, timeout=2),
    )
    request_queues = [q for q in declared if ".reply." not in q["name"]]
    reply_queues = [q for q in declared if ".reply." in q["name"]]
    assert request_queues and all(q["durable"] and not q["exclusive"] for q in request_queues)
    assert reply_queues and all(q["exclusive"] and q["auto_delete"] and not q["durable"] for q in reply_queues)


# -- the shared protocol -------------------------------------------------------------------


class MemoryBackend(PubSubBackend):
    def __init__(self, bus: Bus) -> None:
        self.bus, self.connected, self.closed = bus, False, False

    async def connect(self) -> None:
        self.connected = True

    async def publish(self, topic: str, payload: bytes) -> None:
        await self.bus.publish(topic, payload)

    async def subscribe(self, topic, callback, *, shared_group=None) -> None:
        self.bus.subscribe(topic, callback)

    async def close(self) -> None:
        self.closed = True


def test_topic_names_are_broker_safe_and_stable() -> None:
    assert topic_for("user.created") == "user.created" and topic_for("user.created", "prod.") == "prod.user.created"
    hashed = topic_for('{"cmd": "sum"}')
    assert hashed.startswith("p_") and hashed == topic_for('{"cmd": "sum"}') and " " not in hashed and "{" not in hashed
    assert topic_for("a/b") != topic_for("a.b") and topic_for("a/b").startswith("p_")  # '/' is unsafe on some brokers
    assert topic_for("").startswith("p_")


async def test_protocol_ignores_garbage_and_orphan_replies_and_closes_cleanly() -> None:
    bus = Bus()
    server_backend, client_backend = MemoryBackend(bus), MemoryBackend(bus)
    ms = create_microservice(App, MicroserviceOptions(Transport.CUSTOM, custom_server=PubSubServer(server_backend)))
    await ms.listen()
    assert server_backend.connected
    # a non-JSON message on a handler topic is dropped, not fatal
    await bus.publish("echo.text", b"not json")
    # an unknown reply id (late answer after a timeout) is ignored
    client = PubSubClient(client_backend, timeout=1)
    await client.connect()
    assert await client.request("echo.text", "still works") == "still works"
    reply_topic = next(t for t in bus.subscribers if ".reply." in t)
    await bus.publish(reply_topic, b'{"id": "unknown", "response": 1}')
    await asyncio.sleep(0.05)
    pending = asyncio.create_task(client.request("slow", None))
    await asyncio.sleep(0.05)
    await client.close()  # cancels what's in flight
    with pytest.raises(asyncio.CancelledError):
        await pending
    await ms.close()
    assert client_backend.closed and server_backend.closed


# -- contract: the API our adapters call really exists in the installed libraries ----------


def test_adapters_only_call_api_that_exists_in_the_real_libraries() -> None:
    import aio_pika
    import aiokafka
    import aiomqtt
    import grpc
    import grpc.aio
    import nats
    import nats.aio.client as nats_client
    import redis.asyncio

    params = lambda fn: set(inspect.signature(fn).parameters)  # noqa: E731

    assert inspect.iscoroutinefunction(nats.connect)
    assert {"queue", "cb"} <= params(nats_client.Client.subscribe)
    for method in ("publish", "flush", "drain"):
        assert inspect.iscoroutinefunction(getattr(nats_client.Client, method)), method

    for method in ("start", "stop", "send_and_wait"):
        assert inspect.iscoroutinefunction(getattr(aiokafka.AIOKafkaProducer, method)), method
    assert {"bootstrap_servers"} <= params(aiokafka.AIOKafkaProducer.__init__)
    assert {"bootstrap_servers", "group_id", "auto_offset_reset"} <= params(aiokafka.AIOKafkaConsumer.__init__)
    for method in ("start", "stop", "__anext__"):
        assert inspect.iscoroutinefunction(getattr(aiokafka.AIOKafkaConsumer, method)), method

    assert {"hostname", "port"} <= params(aiomqtt.Client.__init__)
    for method in ("publish", "subscribe", "__aenter__", "__aexit__"):
        assert inspect.iscoroutinefunction(getattr(aiomqtt.Client, method)), method
    assert hasattr(aiomqtt.Client, "messages")

    assert inspect.iscoroutinefunction(aio_pika.connect_robust)
    assert {"body"} <= params(aio_pika.Message.__init__)
    assert {"exclusive", "auto_delete", "durable"} <= params(aio_pika.abc.AbstractChannel.declare_queue)
    assert {"routing_key"} <= params(aio_pika.abc.AbstractExchange.publish)
    assert hasattr(aio_pika.abc.AbstractIncomingMessage, "process")

    for method in ("publish", "pubsub"):
        assert hasattr(redis.asyncio.Redis, method)
    for method in ("subscribe", "get_message", "aclose"):
        assert hasattr(redis.asyncio.client.PubSub, method), method

    assert callable(grpc.aio.server) and callable(grpc.method_handlers_generic_handler)
    assert callable(grpc.unary_unary_rpc_method_handler) and callable(grpc.aio.insecure_channel)


async def test_missing_libraries_produce_install_hints(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__
    blocked = {"redis.asyncio": "redis", "nats": "nats", "aiokafka": "kafka", "aiomqtt": "mqtt", "aio_pika": "rabbitmq"}

    def fake_import(name, *args, **kwargs):
        if name in blocked:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    for transport, extra in (
        (Transport.REDIS, "redis"),
        (Transport.NATS, "nats"),
        (Transport.KAFKA, "kafka"),
        (Transport.MQTT, "mqtt"),
        (Transport.RMQ, "rabbitmq"),
    ):
        ms = create_microservice(App, MicroserviceOptions(transport))
        with pytest.raises(RuntimeError, match=rf"austial-microservices\[{extra}\]"):
            await ms.listen()
    with pytest.raises(ValueError, match="Not a broker transport"):
        from austial.microservices.factory import _backend

        _backend(Transport.TCP, None, "g", {})
