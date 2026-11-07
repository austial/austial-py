from __future__ import annotations

from dataclasses import dataclass

import pytest

from austial import AustialFactory, Injectable, Module
from austial.cqrs import (
    AggregateRoot,
    CommandBus,
    CommandHandler,
    CqrsModule,
    DuplicateHandlerError,
    EventBus,
    EventPublisher,
    EventsHandler,
    HandlerNotFoundError,
    QueryBus,
    QueryHandler,
    Saga,
)

LOG: list[str] = []


@dataclass
class CreateCat:
    name: str


@dataclass
class FindCat:
    name: str


@dataclass
class CatCreated:
    name: str


@dataclass
class CatRenamed:
    old: str
    new: str


@dataclass
class SendWelcome:
    name: str


@Injectable()
class CatsStore:
    def __init__(self) -> None:
        self.cats: dict[str, str] = {}


@CommandHandler(CreateCat)
@Injectable()
class CreateCatHandler:
    def __init__(self, store: CatsStore, events: EventBus):
        self.store, self.events = store, events

    async def execute(self, command: CreateCat) -> str:
        self.store.cats[command.name] = "tabby"
        await self.events.publish(CatCreated(command.name))
        return f"created {command.name}"


@QueryHandler(FindCat)
@Injectable()
class FindCatHandler:
    def __init__(self, store: CatsStore):
        self.store = store

    def execute(self, query: FindCat) -> str | None:  # sync handlers work too
        return self.store.cats.get(query.name)


@EventsHandler(CatCreated)
@Injectable()
class AuditHandler:
    async def handle(self, event: CatCreated) -> None:
        LOG.append(f"audit:{event.name}")


@EventsHandler(CatCreated, CatRenamed)
@Injectable()
class IndexHandler:
    def handle(self, event) -> None:
        LOG.append(f"index:{type(event).__name__}")


@EventsHandler(CatCreated)
@Injectable()
class BrokenHandler:
    def handle(self, event) -> None:
        raise RuntimeError("handler bug")


@Injectable()
class Sagas:
    @Saga()
    def welcome(self, event):
        return SendWelcome(event.name) if isinstance(event, CatCreated) else None

    @Saga()
    def nothing(self, event):
        return None


@CommandHandler(SendWelcome)
@Injectable()
class SendWelcomeHandler:
    def execute(self, command: SendWelcome) -> None:
        LOG.append(f"welcome:{command.name}")


@Module(
    imports=[CqrsModule.for_root()],
    providers=[
        CatsStore,
        CreateCatHandler,
        FindCatHandler,
        AuditHandler,
        IndexHandler,
        BrokenHandler,
        Sagas,
        SendWelcomeHandler,
    ],
)
class CatsApp:
    pass


async def booted():
    app = AustialFactory.create(CatsApp)
    await app.init()
    LOG.clear()
    return app


async def test_command_query_event_and_saga_flow() -> None:
    app = await booted()
    assert await app.get(CommandBus).execute(CreateCat("Tom")) == "created Tom"
    assert await app.get(QueryBus).execute(FindCat("Tom")) == "tabby"
    assert await app.get(QueryBus).execute(FindCat("Nobody")) is None
    # both event handlers ran, the broken one was logged and didn't stop anything, and the saga sent a command
    assert sorted(LOG) == ["audit:Tom", "index:CatCreated", "welcome:Tom"]


async def test_missing_and_duplicate_handlers() -> None:
    app = await booted()
    with pytest.raises(HandlerNotFoundError, match="CatRenamed"):
        await app.get(CommandBus).execute(CatRenamed("a", "b"))
    with pytest.raises(HandlerNotFoundError, match="FindCat"):
        await QueryBus().execute(FindCat("x"))
    with pytest.raises(DuplicateHandlerError):
        app.get(CommandBus).register(CreateCat, object())
    assert app.get(CommandBus).has_handler(CreateCat) and not app.get(QueryBus).has_handler(CreateCat)


async def test_event_handlers_match_subclasses_and_errors_can_propagate() -> None:
    commands = CommandBus()
    strict = EventBus(commands, raise_errors=True)
    seen: list[str] = []

    class Base: ...

    class Child(Base): ...

    class Handler:
        def handle(self, event):
            seen.append(type(event).__name__)

    strict.register(Base, Handler())
    await strict.publish(Child())
    assert seen == ["Child"]

    class Boom:
        def handle(self, event):
            raise ValueError("nope")

    strict.register(Base, Boom())
    with pytest.raises(ValueError, match="nope"):
        await strict.publish(Child())

    def bad_saga(event):
        raise KeyError("saga")

    lenient = EventBus(commands)
    lenient.register_saga(bad_saga)
    await lenient.publish(Child())  # logged, not raised
    with pytest.raises(KeyError):
        await _publish_with(bad_saga)


async def _publish_with(saga):
    bus = EventBus(CommandBus(), raise_errors=True)
    bus.register_saga(saga)
    await bus.publish(object())


async def test_saga_can_return_several_commands() -> None:
    commands = CommandBus()
    ran: list[str] = []

    class Handler:
        def execute(self, command: SendWelcome):
            ran.append(command.name)

    commands.register(SendWelcome, Handler())
    bus = EventBus(commands)
    bus.register_saga(lambda event: [SendWelcome("a"), SendWelcome("b")])
    await bus.publish(object())
    assert ran == ["a", "b"]


# -- aggregates ----------------------------------------------------------------------------


class Cat(AggregateRoot):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    def rename(self, new: str) -> None:
        self.apply(CatRenamed(self.name, new))

    def on_cat_renamed(self, event: CatRenamed) -> None:
        self.name = event.new


async def test_aggregate_apply_commit_and_history() -> None:
    app = await booted()
    publisher = app.get(EventPublisher)
    cat = publisher.merge_object_context(Cat("Tom"))
    assert isinstance(cat, Cat)
    cat.rename("Tommy")
    cat.rename("Thomas")
    assert cat.name == "Thomas" and [e.new for e in cat.uncommitted_events] == ["Tommy", "Thomas"]
    await cat.commit()
    assert cat.uncommitted_events == [] and LOG.count("index:CatRenamed") == 2

    replayed = Cat("Tom")
    replayed.load_from_history([CatRenamed("Tom", "Tommy"), CatRenamed("Tommy", "Thomas")])
    assert replayed.name == "Thomas" and replayed.uncommitted_events == []  # history isn't re-published

    cat.rename("X")
    cat.uncommit()
    assert cat.uncommitted_events == []

    detached = Cat("Loose")
    detached.rename("Y")
    with pytest.raises(RuntimeError, match="isn't connected"):
        await detached.commit()

    Connected = publisher.merge_class_context(Cat)  # noqa: N806
    auto = Connected("Auto")
    auto.rename("Auto2")
    await auto.commit()
    assert Connected.__name__ == "Cat" and isinstance(auto, Cat)
