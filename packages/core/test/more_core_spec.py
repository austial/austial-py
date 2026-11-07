"""INQUIRER, durable providers, Reflector.create_decorator and HttpAdapterHost / get_url."""

from __future__ import annotations

import asyncio
import socket

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from austial import (
    INQUIRER,
    AustialFactory,
    ContextIdFactory,
    ContextIdStrategy,
    Controller,
    Get,
    HttpAdapterHost,
    Inject,
    Injectable,
    Module,
    Reflector,
    Scope,
)
from austial.core.container import Container
from austial.testing import Test

# -- INQUIRER ------------------------------------------------------------------------------


@Injectable()
class LoggerFactory:
    def __init__(self, inquirer=Inject(INQUIRER)):
        self.context = getattr(inquirer, "__name__", None)


@Injectable()
class OrdersService:
    def __init__(self, log: LoggerFactory):
        self.log = log


@Injectable()
class UsersService:
    def __init__(self, log: LoggerFactory):
        self.log = log


@Injectable()
class UsersRepo:
    def __init__(self, log: LoggerFactory):
        self.log = log


async def test_inquirer_gives_each_consumer_its_own_instance_tagged_with_the_consumer() -> None:
    module = await Test.create_testing_module(
        providers=[LoggerFactory, OrdersService, UsersService, UsersRepo]
    ).compile()
    orders, users, repo = module.get(OrdersService), module.get(UsersService), module.get(UsersRepo)
    assert (orders.log.context, users.log.context, repo.log.context) == ("OrdersService", "UsersService", "UsersRepo")
    assert orders.log is not users.log  # never shared: it's built per consumer
    assert module.get(OrdersService) is orders  # the consumer itself is still a singleton


def test_inquirer_in_a_factory_provider_is_the_factory_token() -> None:
    container = Container()
    container.register({"provide": "TAGGED", "useFactory": lambda who: who, "inject": [INQUIRER]})

    @Injectable()
    class Consumer:
        def __init__(self, tagged=Inject("TAGGED")):
            self.tagged = tagged

    assert container.resolve(Consumer).tagged is Consumer
    assert container.resolve(INQUIRER) is None  # asked for outside any consumer


# -- durable providers ---------------------------------------------------------------------

BUILT: list[str] = []


@Injectable(scope=Scope.REQUEST, durable=True)
class TenantConnection:
    def __init__(self) -> None:
        BUILT.append("tenant-connection")
        self.id = len(BUILT)


@Injectable(scope=Scope.REQUEST)
class PerRequest:
    def __init__(self) -> None:
        BUILT.append("per-request")


@Controller("tenant")
class TenantController:
    def __init__(self, conn: TenantConnection, per_request: PerRequest):
        self.conn = conn

    @Get()
    async def get(self):
        return {"conn": self.conn.id}


class HeaderStrategy(ContextIdStrategy):
    def get_key(self, request):
        return request.headers.get("x-tenant")  # None -> no durable sharing


async def test_durable_providers_are_shared_per_context_key() -> None:
    BUILT.clear()
    ContextIdFactory.apply_strategy(HeaderStrategy())
    try:
        module = await Test.create_testing_module(
            controllers=[TenantController], providers=[TenantConnection, PerRequest]
        ).compile()
        app = module.create_austial_application()
        await app.init()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            a1 = (await client.get("/tenant", headers={"x-tenant": "acme"})).json()
            a2 = (await client.get("/tenant", headers={"x-tenant": "acme"})).json()
            b1 = (await client.get("/tenant", headers={"x-tenant": "globex"})).json()
            anon1 = (await client.get("/tenant")).json()
            anon2 = (await client.get("/tenant")).json()
    finally:
        ContextIdFactory.apply_strategy(None)

    assert a1 == a2  # same tenant -> the same connection, across requests
    assert b1 != a1  # another tenant -> its own
    assert anon1 != anon2  # no key -> behaves like plain request scope
    assert BUILT.count("per-request") == 5  # non-durable request providers are still per request
    assert BUILT.count("tenant-connection") == 4  # acme once, globex once, two anonymous


async def test_durable_without_a_strategy_is_plain_request_scope() -> None:
    BUILT.clear()
    module = await Test.create_testing_module(
        controllers=[TenantController], providers=[TenantConnection, PerRequest]
    ).compile()
    app = module.create_austial_application()
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = (await client.get("/tenant", headers={"x-tenant": "acme"})).json()
        second = (await client.get("/tenant", headers={"x-tenant": "acme"})).json()
    assert first != second


# -- Reflector.create_decorator ------------------------------------------------------------


def test_reflector_create_decorator_roundtrip() -> None:
    Roles = Reflector.create_decorator()  # noqa: N806
    Public = Reflector.create_decorator()  # noqa: N806
    Tagged = Reflector.create_decorator(key="my:tags", transform=lambda v: sorted(set(v)))  # noqa: N806
    assert Roles.KEY != Public.KEY and Tagged.KEY == "my:tags"

    @Roles(["admin"])
    class Controller_:
        @Roles(["editor"])
        def handler(self): ...

        @Public()
        def open(self): ...

        @Tagged(["b", "a", "b"])
        def tagged(self): ...

        def bare(self): ...

    reflector = Reflector()
    assert reflector.get(Roles, Controller_.handler) == ["editor"]
    assert reflector.get(Public, Controller_.open) is True
    assert reflector.get(Public, Controller_.bare) is None and reflector.get(Public, Controller_.bare, "d") == "d"
    assert reflector.get(Tagged, Controller_.tagged) == ["a", "b"]
    assert reflector.get_all_and_override(Roles, [Controller_.bare, Controller_]) == ["admin"]
    assert reflector.get_all_and_merge(Roles, [Controller_.handler, Controller_]) == ["editor", "admin"]


# -- HttpAdapterHost, get_url, TLS options --------------------------------------------------


@Injectable()
class NeedsHost:
    def __init__(self, host: HttpAdapterHost):
        self.host = host


async def test_http_adapter_host_exposes_the_fastapi_app() -> None:
    from fastapi import FastAPI

    @Module(providers=[NeedsHost])
    class Root:
        pass

    app = AustialFactory.create(Root)
    assert app.get(NeedsHost).host.http_adapter is app.get_http_adapter()
    assert isinstance(app.get(HttpAdapterHost).http_adapter, FastAPI)

    module = await Test.create_testing_module(providers=[NeedsHost]).compile()
    testing_app = module.create_austial_application()
    assert module.get(NeedsHost).host.http_adapter is testing_app.get_http_adapter()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def test_listen_records_the_url_and_server() -> None:
    @Controller("ping")
    class PingController:
        @Get()
        async def ping(self):
            return "pong"

    @Module(controllers=[PingController])
    class Root:
        pass

    app = AustialFactory.create(Root)
    with pytest.raises(RuntimeError, match="isn't listening"):
        app.get_url()
    assert app.get_http_server() is None

    port = _free_port()
    task = asyncio.create_task(app.listen(port=port, host="127.0.0.1"))
    try:
        for _ in range(100):
            server = app.get_http_server()
            if server is not None and server.started:
                break
            await asyncio.sleep(0.05)
        assert app.get_url() == f"http://127.0.0.1:{port}"
        async with httpx.AsyncClient() as client:
            assert (await client.get(f"{app.get_url()}/ping")).json() == "pong"
    finally:
        app.get_http_server().should_exit = True
        await asyncio.wait_for(task, timeout=10)


async def test_listen_passes_tls_options_through(tmp_path, monkeypatch) -> None:
    captured: dict = {}

    class FakeServer:
        def __init__(self, config) -> None:
            captured["config"] = config

        async def serve(self) -> None:
            return None

    import uvicorn

    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    monkeypatch.setattr(uvicorn.Config, "load", lambda self: None, raising=False)

    @Module()
    class Root:
        pass

    app = AustialFactory.create(Root)
    await app.listen(
        port=8443, host="0.0.0.0", ssl_certfile=str(tmp_path / "c.pem"), ssl_keyfile=str(tmp_path / "k.pem")
    )
    assert app.get_url() == "https://127.0.0.1:8443"
    assert captured["config"].ssl_certfile.endswith("c.pem")
