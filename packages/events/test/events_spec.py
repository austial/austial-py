from __future__ import annotations

import asyncio

import pytest

from austial import AustialFactory, Controller, Get, Injectable, Module
from austial.events import EventEmitter, EventEmitterModule, EventEmitterOptions, OnEvent
from austial.testing import Test


def make(**options) -> EventEmitter:
    return EventEmitter(EventEmitterOptions(**options))


# ---------------------------------------------------------------------------------------------
# emitter
# ---------------------------------------------------------------------------------------------


def test_emit_calls_sync_handlers_with_arguments_and_reports_listeners() -> None:
    emitter = make()
    seen: list = []
    emitter.on("greet", lambda who, punct="!": seen.append((who, punct)))
    assert emitter.emit("greet", "ada") is True
    assert emitter.emit("nobody") is False
    assert seen == [("ada", "!")]


@pytest.mark.parametrize(
    ("pattern", "event", "expected"),
    [
        ("order.created", "order.created", True),
        ("order.*", "order.created", True),
        ("order.*", "order.created.eu", False),
        ("order.**", "order.created.eu", True),
        ("order.**", "order", True),
        ("**", "a.b.c", True),
        ("*.failed", "payment.failed", True),
        ("*.failed", "a.b.failed", False),
        ("**.failed", "a.b.failed", True),
        ("order.*", "invoice.created", False),
        ("a.*.c", "a.b.c", True),
        ("a.*.c", "a.c", False),
    ],
)
def test_wildcard_matching(pattern: str, event: str, expected: bool) -> None:
    emitter = make()
    hits: list[str] = []
    emitter.on(pattern, lambda: hits.append(event))
    emitter.emit(event)
    assert bool(hits) is expected


def test_wildcards_can_be_disabled_and_delimiter_changed() -> None:
    literal = make(wildcard=False)
    hits: list[int] = []
    literal.on("order.*", lambda: hits.append(1))
    literal.emit("order.created")
    assert hits == []
    literal.emit("order.*")
    assert hits == [1]

    colon = make(delimiter=":")
    colon.on("order:*", lambda: hits.append(2))
    colon.emit("order:created")
    assert hits == [1, 2]


def test_once_prepend_off_and_unsubscribe() -> None:
    emitter = make()
    order: list[str] = []
    emitter.on("e", lambda: order.append("a"))
    emitter.on("e", lambda: order.append("first"), prepend=True)
    emitter.once("e", lambda: order.append("once"))
    emitter.emit("e")
    emitter.emit("e")
    assert order == ["first", "a", "once", "first", "a"]

    handler = lambda: order.append("x")  # noqa: E731
    unsubscribe = emitter.on("z", handler)
    assert emitter.listener_count("z") == 1 and emitter.listeners("z") == [handler]
    unsubscribe()
    assert emitter.listener_count("z") == 0
    emitter.on("z", handler)
    emitter.off("z", handler)
    assert emitter.listener_count("z") == 0
    emitter.on("a", handler)
    emitter.on("b", handler)
    emitter.remove_all_listeners("a")
    assert emitter.listener_count("a") == 0 and emitter.listener_count("b") == 1
    emitter.remove_all_listeners()
    assert emitter.listener_count("b") == 0


def test_max_listeners_guards_against_leaks() -> None:
    emitter = make(max_listeners=1)
    emitter.on("e", lambda: None)
    with pytest.raises(RuntimeError, match="Too many listeners"):
        emitter.on("e", lambda: None)


def test_sync_handler_errors_are_suppressed_by_default_but_can_propagate() -> None:
    emitter = make()
    after: list[int] = []
    emitter.on("e", lambda: 1 / 0)
    emitter.on("e", lambda: after.append(1))
    emitter.emit("e")
    assert after == [1]  # the failing handler didn't stop the next one

    strict = make(suppress_errors=False)
    strict.on("e", lambda: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        strict.emit("e")


async def test_emit_runs_async_handlers_in_the_background() -> None:
    emitter = make()
    done: list[str] = []

    async def slow(value: str) -> None:
        await asyncio.sleep(0.01)
        done.append(value)

    async def failing(value: str) -> None:
        raise RuntimeError("background failure")

    emitter.on("e", slow)
    emitter.on("e", failing)
    assert emitter.emit("e", "v") is True
    assert done == []  # not finished yet: emit() doesn't wait
    await emitter.wait_idle()
    assert done == ["v"]  # and the failing one didn't take the process down


async def test_emit_async_awaits_everything_and_returns_results_in_order() -> None:
    emitter = make()

    async def double(n: int) -> int:
        await asyncio.sleep(0.01)
        return n * 2

    emitter.on("calc", double)
    emitter.on("calc", lambda n: n + 1)
    emitter.on("calc", lambda n: 1 / 0)  # suppressed -> None
    assert await emitter.emit_async("calc", 5) == [10, 6, None]
    assert await emitter.emit_async("nobody") == []

    strict = make(suppress_errors=False)
    strict.on("e", lambda: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        await strict.emit_async("e")

    emitter.once("once", lambda: "x")
    assert await emitter.emit_async("once") == ["x"]
    assert await emitter.emit_async("once") == []


# ---------------------------------------------------------------------------------------------
# @OnEvent + the module
# ---------------------------------------------------------------------------------------------

LOG: list[str] = []


@Injectable()
class Receipts:
    @OnEvent("order.created")
    async def send(self, order: dict) -> str:
        LOG.append(f"receipt:{order['id']}")
        return "sent"

    @OnEvent(["order.created", "order.updated"], prepend=True)
    def audit(self, order: dict) -> None:
        LOG.append(f"audit:{order['id']}")

    @OnEvent("order.*")
    @OnEvent("invoice.paid", once=True)
    def stacked(self, payload: dict) -> None:
        LOG.append("stacked")

    def not_a_handler(self) -> None:
        raise AssertionError("must not be subscribed")


@Controller("hooks")
class HooksController:
    @OnEvent("controller.event")
    def handle(self, *args) -> None:
        LOG.append("controller-handler")

    @Get()
    async def get(self):
        return "ok"


@Module(controllers=[HooksController], providers=[Receipts], imports=[EventEmitterModule.for_root()])
class EventsApp:
    pass


async def test_on_event_handlers_are_wired_when_the_app_initialises() -> None:
    LOG.clear()
    app = AustialFactory.create(EventsApp)
    emitter = app.get(EventEmitter)
    assert emitter.listener_count("order.created") == 0  # nothing subscribed before bootstrap
    await app.init()

    results = await emitter.emit_async("order.created", {"id": 7})
    assert LOG == ["audit:7", "receipt:7", "stacked"]  # prepend put audit first; `order.*` matched too
    assert "sent" in results

    LOG.clear()
    emitter.emit("controller.event")
    assert LOG == ["controller-handler"]

    LOG.clear()
    await emitter.emit_async("invoice.paid", {})
    await emitter.emit_async("invoice.paid", {})
    assert LOG == ["stacked"]  # the once=True handler fired a single time


async def test_module_options_flow_into_the_emitter() -> None:
    module = await Test.create_testing_module(
        imports=[EventEmitterModule.for_root(wildcard=False, delimiter=":", max_listeners=3, suppress_errors=False)]
    ).compile()
    options = module.get(EventEmitter).options
    assert (options.wildcard, options.delimiter, options.max_listeners, options.suppress_errors) == (
        False,
        ":",
        3,
        False,
    )
