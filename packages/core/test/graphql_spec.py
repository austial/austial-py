from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import strawberry
from httpx import ASGITransport, AsyncClient
from strawberry.types import Info

from austial import AustialFactory, Injectable, Module, Scope
from austial.graphql import GraphQLModule, inject


@Injectable()
class GreetingService:
    def greet(self, name: str) -> str:
        return f"Hello, {name}!"


@Injectable(scope=Scope.REQUEST)
class RequestCounter:
    created = 0

    def __init__(self) -> None:
        RequestCounter.created += 1
        self.value = RequestCounter.created


@strawberry.type
class Query:
    @strawberry.field
    def greeting(self, info: Info, name: str = "world") -> str:
        return inject(info, GreetingService).greet(name)

    @strawberry.field
    def counter(self, info: Info) -> int:
        # resolved twice in one GraphQL request -> the same request-scoped instance
        assert inject(info, RequestCounter) is inject(info, RequestCounter)
        return inject(info, RequestCounter).value

    @strawberry.field
    def user(self, info: Info) -> str:
        return info.context.get("user", "anonymous")

    @strawberry.field
    def header(self, info: Info) -> str:
        return info.context["request"].headers.get("x-test", "-")


@strawberry.type
class Mutation:
    @strawberry.mutation
    def shout(self, info: Info, text: str) -> str:
        return inject(info, GreetingService).greet(text).upper()


schema = strawberry.Schema(query=Query, mutation=Mutation)


def make_app(**options):
    @Module(imports=[GraphQLModule.for_root(schema=schema, **options)], providers=[GreetingService, RequestCounter])
    class Root:
        pass

    return AustialFactory.create(Root)


async def run(app, query: str, **kwargs):
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(kwargs.pop("path", "/graphql"), json={"query": query}, **kwargs)


async def test_resolvers_use_dependency_injection() -> None:
    response = await run(make_app(), '{ greeting(name: "Ada") }')
    assert response.json() == {"data": {"greeting": "Hello, Ada!"}}


async def test_mutations_work() -> None:
    response = await run(make_app(), 'mutation { shout(text: "hi") }')
    assert response.json() == {"data": {"shout": "HELLO, HI!"}}


async def test_request_scoped_providers_are_built_once_per_graphql_request() -> None:
    RequestCounter.created = 0
    app = make_app()
    first = (await run(app, "{ counter }")).json()["data"]["counter"]
    second = (await run(app, "{ counter }")).json()["data"]["counter"]
    assert (first, second) == (1, 2)


async def test_context_getter_adds_to_the_context_and_request_is_available() -> None:
    app = make_app(context_getter=lambda request: {"user": request.headers.get("x-user", "anonymous")})
    response = await run(app, "{ user header }", headers={"x-user": "ada", "x-test": "yes"})
    assert response.json()["data"] == {"user": "ada", "header": "yes"}

    async def async_getter(request):
        return {"user": "async-user"}

    assert (await run(make_app(context_getter=async_getter), "{ user }")).json()["data"]["user"] == "async-user"


async def test_custom_path_ide_and_graphql_errors() -> None:
    app = make_app(path="/api/graphql", ide="graphiql")
    ok = await run(app, '{ greeting(name: "x") }', path="/api/graphql")
    assert ok.json()["data"]["greeting"] == "Hello, x!"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        page = await client.get("/api/graphql", headers={"accept": "text/html"})
        assert page.status_code == 200 and "graphiql" in page.text.lower()
        bad = await client.post("/api/graphql", json={"query": "{ nope }"})
        assert bad.json()["errors"][0]["message"].startswith("Cannot query field")

    no_ide = make_app(ide=None)
    await no_ide.init()
    async with AsyncClient(transport=ASGITransport(app=no_ide), base_url="http://test") as client:
        assert (await client.get("/graphql", headers={"accept": "text/html"})).status_code != 200


async def test_schema_factory_receives_the_module_ref() -> None:
    seen = {}

    def factory(module_ref):
        seen["service"] = module_ref.get(GreetingService)
        return schema

    @Module(imports=[GraphQLModule.for_root(schema=factory)], providers=[GreetingService, RequestCounter])
    class Root:
        pass

    app = AustialFactory.create(Root)
    assert (await run(app, '{ greeting(name: "f") }')).json()["data"]["greeting"] == "Hello, f!"
    assert isinstance(seen["service"], GreetingService)


async def test_helpful_error_when_strawberry_is_missing(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("strawberry"):
            raise ImportError("no strawberry")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match=r"austial-core\[strawberry\]"):
        await make_app().init()


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def count(self, info: Info, to: int = 3) -> AsyncGenerator[str, None]:
        greeting = inject(info, GreetingService)  # DI works over the WebSocket too
        for n in range(to):
            yield f"{greeting.greet(str(n))}"


def test_subscriptions_over_websocket():
    from starlette.testclient import TestClient

    sub_schema = strawberry.Schema(query=Query, subscription=Subscription)

    @Module(imports=[GraphQLModule.for_root(schema=sub_schema)], providers=[GreetingService, RequestCounter])
    class SubRoot:
        pass

    with (
        TestClient(AustialFactory.create(SubRoot)) as client,
        client.websocket_connect("/graphql", subprotocols=["graphql-transport-ws"]) as ws,
    ):
        ws.send_json({"type": "connection_init"})
        assert ws.receive_json()["type"] == "connection_ack"
        ws.send_json({"id": "1", "type": "subscribe", "payload": {"query": "subscription { count(to: 2) }"}})
        first, second = ws.receive_json(), ws.receive_json()
        assert first["payload"]["data"] == {"count": "Hello, 0!"}
        assert second["payload"]["data"] == {"count": "Hello, 1!"}
        assert ws.receive_json()["type"] == "complete"
