from __future__ import annotations

from typing import Any

import pytest

from austial import AustialFactory, Injectable, Module
from austial.mongo import (
    InjectClient,
    InjectCollection,
    InjectDatabase,
    MongoModule,
    MongoOptions,
)
from austial.testing import Test


class FakeCollection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.docs: list[dict] = []

    async def insert_one(self, doc: dict) -> None:
        self.docs.append(doc)


class FakeDatabase:
    def __init__(self, name: str) -> None:
        self.name = name
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection(name))


class FakeAdmin:
    def __init__(self, client: FakeClient) -> None:
        self.client = client

    async def command(self, name: str) -> dict:
        self.client.commands.append(name)
        if self.client.fail:
            raise ConnectionError("server selection timed out")
        return {"ok": 1}


class FakeClient:
    instances: list[FakeClient] = []

    def __init__(self, uri: str, **kwargs: Any) -> None:
        self.uri, self.kwargs, self.closed, self.fail = uri, kwargs, False, False
        self.commands: list[str] = []
        self.databases: dict[str, FakeDatabase] = {}
        self.admin = FakeAdmin(self)
        FakeClient.instances.append(self)

    def __getitem__(self, name: str) -> FakeDatabase:
        return self.databases.setdefault(name, FakeDatabase(name))

    async def close(self) -> None:
        self.closed = True


@Injectable()
class CatsService:
    def __init__(self, cats=InjectCollection("cats"), db=InjectDatabase(), client=InjectClient()):
        self.cats, self.db, self.client = cats, db, client


def root(**options):
    @Module(
        imports=[
            MongoModule.for_root(uri="mongodb://db:27017", database="zoo", client_factory=FakeClient, **options),
            MongoModule.for_feature(["cats", "owners"]),
        ],
        providers=[CatsService],
    )
    class Root:
        pass

    return Root


async def test_collections_database_and_client_are_injectable() -> None:
    FakeClient.instances.clear()
    app = AustialFactory.create(root(maxPoolSize=7))
    await app.init()
    service = app.get(CatsService)
    assert isinstance(service.client, FakeClient) and service.client.uri == "mongodb://db:27017"
    assert service.client.kwargs == {"maxPoolSize": 7}  # extra options reach the client
    assert service.db is service.client["zoo"]
    assert service.cats is service.db["cats"] and service.cats.name == "cats"
    await service.cats.insert_one({"name": "Tom"})
    assert service.cats.docs == [{"name": "Tom"}]
    assert len(FakeClient.instances) == 1  # one shared client


async def test_pings_on_init_and_closes_on_shutdown() -> None:
    app = AustialFactory.create(root())
    await app.init()
    client = app.get(CatsService).client
    assert client.commands == ["ping"] and not client.closed
    await app.close()
    assert client.closed


async def test_startup_fails_fast_when_the_server_is_unreachable() -> None:
    @Module(imports=[MongoModule.for_root(client_factory=FakeClient)])
    class Bad:
        pass

    app = AustialFactory.create(Bad)
    app.get("AUSTIAL_MONGO_CLIENT").fail = True
    with pytest.raises(ConnectionError, match="timed out"):
        await app.init()


async def test_connect_on_init_can_be_disabled_and_async_options() -> None:
    app = AustialFactory.create(root(connect_on_init=False))
    await app.init()
    assert app.get(CatsService).client.commands == []

    module = await Test.create_testing_module(
        imports=[
            MongoModule.for_root_async(
                use_factory=lambda: MongoOptions(uri="mongodb://async", database="d", client_factory=FakeClient)
            )
        ]
    ).compile()
    assert module.get("AUSTIAL_MONGO_CLIENT").uri == "mongodb://async"


async def test_real_pymongo_client_is_created_lazily_without_connecting() -> None:
    pymongo = pytest.importorskip("pymongo")

    @Module(imports=[MongoModule.for_root(uri="mongodb://127.0.0.1:1/", database="x", connect_on_init=False)])
    class Real:
        pass

    app = AustialFactory.create(Real)
    client = app.get("AUSTIAL_MONGO_CLIENT")
    assert isinstance(client, pymongo.AsyncMongoClient)
    assert app.get("AUSTIAL_MONGO_DATABASE").name == "x"
    await client.close()


async def test_helpful_error_without_pymongo(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pymongo":
            raise ImportError("no pymongo")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    @Module(imports=[MongoModule.for_root()])
    class NoDriver:
        pass

    with pytest.raises(RuntimeError, match=r"austial-orm\[pymongo\]"):
        AustialFactory.create(NoDriver).get("AUSTIAL_MONGO_CLIENT")
