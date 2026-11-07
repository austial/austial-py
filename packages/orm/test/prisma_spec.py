from __future__ import annotations

from austial import AustialFactory, Injectable, Module
from austial.prisma import PrismaModule


class FakePrisma:
    """Stands in for the generated `prisma.Prisma` client."""

    instances: list[FakePrisma] = []

    def __init__(self, **options) -> None:
        self.options = options
        self.events: list[str] = []
        self._connected = False
        FakePrisma.instances.append(self)

    async def connect(self) -> None:
        self.events.append("connect")
        self._connected = True

    async def disconnect(self) -> None:
        self.events.append("disconnect")
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected


@Injectable()
class CatsService:
    def __init__(self, db: FakePrisma):
        self.db = db


async def test_class_is_built_injected_by_type_and_tied_to_the_lifecycle() -> None:
    FakePrisma.instances.clear()

    @Module(imports=[PrismaModule.for_root(FakePrisma, log_queries=True)], providers=[CatsService])
    class Root:
        pass

    app = AustialFactory.create(Root)
    await app.init()
    db = app.get(CatsService).db
    assert isinstance(db, FakePrisma) and db.options == {"log_queries": True}
    assert db.events == ["connect"] and len(FakePrisma.instances) == 1
    await app.close()
    assert db.events == ["connect", "disconnect"]


async def test_instances_connect_false_and_already_disconnected() -> None:
    instance = FakePrisma()

    @Module(imports=[PrismaModule.for_root(instance, connect=False)], providers=[CatsService])
    class Root:
        pass

    app = AustialFactory.create(Root)
    await app.init()
    assert app.get(CatsService).db is instance and instance.events == []  # connect=False: left to the caller
    await app.close()
    assert instance.events == []  # never connected -> nothing to disconnect


async def test_clients_without_is_connected_are_always_disconnected() -> None:
    class Minimal:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def connect(self) -> None:
            self.calls.append("connect")

        async def disconnect(self) -> None:
            self.calls.append("disconnect")

    @Module(imports=[PrismaModule.for_root(Minimal)])
    class Root:
        pass

    app = AustialFactory.create(Root)
    await app.init()
    client = app.get(Minimal)
    await app.close()
    assert client.calls == ["connect", "disconnect"]
