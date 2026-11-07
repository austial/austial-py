from __future__ import annotations

import asyncio
import socket
from typing import Any

import pytest

from austial import (
    AustialFactory,
    CanActivate,
    Controller,
    ExecutionContext,
    Get,
    Inject,
    Injectable,
    Module,
    NestInterceptor,
    UseGuards,
    UseInterceptors,
)
from austial.microservices import (
    ClientOptions,
    ClientProxy,
    ClientsModule,
    Ctx,
    EventPattern,
    MessagePattern,
    MicroserviceOptions,
    Payload,
    RpcContext,
    RpcError,
    RpcException,
    Transport,
    create_microservice,
    pattern_key,
)
from austial.microservices.transport import ClientTransport, ServerTransport

EVENTS: list = []


class DenyGuard(CanActivate):
    async def can_activate(self, context: ExecutionContext) -> bool:
        assert context.get_type() == "rpc" and context.switch_to_rpc().get_context().kind == "request"
        return context.switch_to_rpc().get_data() != "forbidden"


class Double(NestInterceptor):
    async def intercept(self, context, next):
        return (await next.handle()) * 2


@Injectable()
class Math:
    @MessagePattern({"cmd": "sum"})
    def accumulate(self, numbers: list[int] = Payload()) -> int:
        return sum(numbers)

    @MessagePattern("echo")
    async def echo(self, data):  # an unmarked first parameter is the payload
        return data

    @MessagePattern("pick")
    def pick(self, who: str = Payload("who"), ctx: RpcContext = Ctx()):
        return f"{who} via {ctx.pattern}"

    @MessagePattern("fail")
    def fail(self):
        raise RpcException({"status": "error", "message": "bad input", "code": 42})

    @MessagePattern("bug")
    def bug(self):
        raise ZeroDivisionError("oops")

    @MessagePattern("guarded")
    @UseGuards(DenyGuard)
    def guarded(self, data):
        return "ok"

    @MessagePattern("doubled")
    @UseInterceptors(Double)
    def doubled(self, data):
        return data

    @MessagePattern("slow")
    async def slow(self):
        await asyncio.sleep(1)

    @EventPattern("user.created")
    @EventPattern("user.updated")
    def on_user(self, user: dict = Payload()):
        EVENTS.append(("user", user))

    @EventPattern("explodes")
    def explodes(self):
        raise RuntimeError("event bug")


@Controller()
class AlsoHandlers:
    @MessagePattern("from-controller")
    def handler(self, data):
        return "controller-ok"


@Module(controllers=[AlsoHandlers], providers=[Math, DenyGuard, Double])
class MathModule:
    pass


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def tcp_pair():
    port = free_port()
    ms = create_microservice(MathModule, MicroserviceOptions(Transport.TCP, port=port))
    await ms.listen()
    client = ClientProxy(ClientOptions(name="MATH", port=port, timeout=2))
    await client.connect()
    return ms, client


async def test_tcp_request_response_events_and_patterns() -> None:
    EVENTS.clear()
    ms, client = await tcp_pair()
    try:
        assert await client.send({"cmd": "sum"}, [1, 2, 3]) == 6
        assert await client.send("echo", {"a": [1, None]}) == {"a": [1, None]}
        assert await client.send("pick", {"who": "ada"}) == "ada via pick"
        assert await client.send("from-controller") == "controller-ok"
        assert await client.send("doubled", 21) == 42  # interceptors apply
        assert await client.send("guarded", "fine") == "ok"

        await client.emit("user.created", {"id": 1})
        await client.emit("user.updated", {"id": 2})
        await client.emit("explodes")  # a failing event handler is logged, never reported to the sender
        await client.emit("nobody-listens")
        for _ in range(100):
            if len(EVENTS) == 2:
                break
            await asyncio.sleep(0.01)
        assert EVENTS == [("user", {"id": 1}), ("user", {"id": 2})]
    finally:
        await client.close()
        await ms.close()


async def test_tcp_errors_timeouts_and_concurrency() -> None:
    ms, client = await tcp_pair()
    try:
        with pytest.raises(RpcError) as caught:
            await client.send("fail")
        assert caught.value.payload == {"status": "error", "message": "bad input", "code": 42}
        with pytest.raises(RpcError, match="ZeroDivisionError"):
            await client.send("bug")
        with pytest.raises(RpcError, match="Forbidden"):
            await client.send("guarded", "forbidden")
        with pytest.raises(RpcError, match="no matching message handler"):
            await client.send("unknown")
        with pytest.raises(asyncio.TimeoutError):
            await client.send("slow", timeout=0.05)
        # many calls in flight over one connection each get their own answer
        results = await asyncio.gather(*(client.send({"cmd": "sum"}, [n, n]) for n in range(20)))
        assert results == [n * 2 for n in range(20)]
    finally:
        await client.close()
        await ms.close()


async def test_closing_the_server_fails_calls_in_flight() -> None:
    ms, client = await tcp_pair()
    call = asyncio.create_task(client.send("slow", timeout=5))
    await asyncio.sleep(0.05)
    await ms.close()
    with pytest.raises((ConnectionError, RpcError, asyncio.TimeoutError)):
        await call
    await client.close()


async def test_local_transport_and_missing_broker() -> None:
    ms = create_microservice(MathModule, MicroserviceOptions(Transport.LOCAL, name="math"))
    await ms.listen()
    client = ClientProxy(ClientOptions(name="M", transport=Transport.LOCAL, broker="math"))
    try:
        assert await client.send({"cmd": "sum"}, [4, 5]) == 9
        with pytest.raises(RpcException):
            await client.send("fail")
    finally:
        await ms.close()
    with pytest.raises(ConnectionError, match="No local microservice"):
        await client.send("echo", 1)


def test_pattern_keys_are_stable() -> None:
    assert pattern_key("a.b") == "a.b"
    assert pattern_key({"b": 1, "a": 2}) == pattern_key({"a": 2, "b": 1}) == '{"a": 2, "b": 1}'


# -- ClientsModule, custom transports, hybrid ----------------------------------------------


@Injectable()
class Calculator:
    def __init__(self, math: ClientProxy = Inject("MATH")):
        self.math = math

    async def total(self, numbers: list[int]) -> int:
        return await self.math.send({"cmd": "sum"}, numbers)


async def test_clients_module_connects_with_the_app_and_injects_proxies() -> None:
    server = create_microservice(MathModule, MicroserviceOptions(Transport.LOCAL, name="calc"))
    await server.listen()

    @Module(
        imports=[ClientsModule.register([ClientOptions(name="MATH", transport=Transport.LOCAL, broker="calc")])],
        providers=[Calculator],
    )
    class ClientApp:
        pass

    app = AustialFactory.create(ClientApp)
    await app.init()
    try:
        assert await app.get(Calculator).total([1, 2, 3, 4]) == 10
    finally:
        await app.close()
        await server.close()


async def test_custom_transport() -> None:
    log: list = []

    class MemServer(ServerTransport):
        handler: Any = None

        async def listen(self, handler):
            MemServer.handler = handler
            log.append("listening")

        async def close(self):
            log.append("closed")

    class MemClient(ClientTransport):
        async def connect(self):
            log.append("connected")

        async def request(self, pattern, data):
            return await MemServer.handler("request", pattern, data)

        async def emit(self, pattern, data):
            await MemServer.handler("event", pattern, data)

        async def close(self):
            log.append("client-closed")

    ms = create_microservice(MathModule, MicroserviceOptions(Transport.CUSTOM, custom_server=MemServer()))
    await ms.listen()
    client = ClientProxy(ClientOptions(name="X", transport=Transport.CUSTOM, custom_client=MemClient()))
    await client.connect()
    assert await client.send("echo", "via custom") == "via custom"
    await client.close()
    await ms.close()
    assert log == ["listening", "connected", "client-closed", "closed"]

    with pytest.raises(ValueError, match="custom_server"):
        create_microservice(MathModule, MicroserviceOptions(Transport.CUSTOM))
    with pytest.raises(ValueError, match="custom_client"):
        ClientProxy(ClientOptions(name="Y", transport=Transport.CUSTOM))


@Controller("web")
class WebController:
    @Get()
    async def get(self):
        return "http-ok"


@Module(controllers=[WebController, AlsoHandlers], providers=[Math])
class HybridModule:
    pass


async def test_hybrid_app_serves_http_and_rpc_and_stops_together() -> None:
    from httpx import ASGITransport, AsyncClient

    app = AustialFactory.create(HybridModule)
    app.connect_microservice(MicroserviceOptions(Transport.LOCAL, name="hybrid"))
    await app.init()  # starts the transport after the init hooks
    rpc = ClientProxy(ClientOptions(name="H", transport=Transport.LOCAL, broker="hybrid"))
    try:
        assert await rpc.send({"cmd": "sum"}, [5, 5]) == 10
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            assert (await http.get("/web")).json() == "http-ok"
    finally:
        await app.close()
    with pytest.raises(ConnectionError):
        await rpc.send("echo", 1)  # the transport stopped with the application


async def test_hybrid_manual_start() -> None:
    app = AustialFactory.create(HybridModule)
    app.connect_microservice(MicroserviceOptions(Transport.LOCAL, name="manual"), auto_start=False)
    await app.init()
    rpc = ClientProxy(ClientOptions(name="H", transport=Transport.LOCAL, broker="manual"))
    with pytest.raises(ConnectionError):
        await rpc.send("echo", 1)  # not started yet
    await app.start_all_microservices()
    try:
        assert await rpc.send("echo", "now") == "now"
    finally:
        await app._microservices[0].stop()  # noqa: SLF001
        await app.close()


async def test_factory_create_microservice_and_duplicate_patterns() -> None:
    ms = AustialFactory.create_microservice(MathModule, MicroserviceOptions(Transport.LOCAL, name="factory"))
    await ms.listen()
    assert ms.server.running
    await ms.close()
    assert not ms.server.running

    @Injectable()
    class First:
        @MessagePattern("dup")
        def a(self): ...

    @Injectable()
    class Second:
        @MessagePattern("dup")
        def b(self): ...

    @Module(providers=[First, Second])
    class Dup:
        pass

    clash = create_microservice(Dup, MicroserviceOptions(Transport.LOCAL, name="dup"))
    with pytest.raises(RuntimeError, match="Two handlers"):
        await clash.listen()
