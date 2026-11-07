"""``AggregateRoot`` and ``EventPublisher`` -- mirror ``@nestjs/cqrs``.

::

    class Cat(AggregateRoot):
        def __init__(self, id): super().__init__(); self.id = id; self.name = None

        def rename(self, name):
            self.apply(CatRenamed(self.id, name))      # records the event and calls on_cat_renamed

        def on_cat_renamed(self, event):               # state change -- also used when replaying history
            self.name = event.name

    cat = publisher.merge_object_context(Cat(1))
    cat.rename("Tom")
    await cat.commit()                                  # publishes the uncommitted events on the EventBus
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from austial.cqrs.buses import EventBus


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class AggregateRoot:
    def __init__(self) -> None:
        self._uncommitted: list[Any] = []
        self._publisher: EventBus | None = None

    @property
    def uncommitted_events(self) -> list[Any]:
        return list(self._uncommitted)

    def apply(self, event: Any, *, from_history: bool = False) -> None:
        """Runs ``on_<event_class_snake_case>`` (if defined) and, unless replaying history, queues the event."""
        handler = getattr(self, f"on_{_snake(type(event).__name__)}", None)
        if callable(handler):
            handler(event)
        if not from_history:
            self._uncommitted.append(event)

    def load_from_history(self, events: Iterable[Any]) -> None:
        for event in events:
            self.apply(event, from_history=True)

    async def commit(self) -> None:
        """Publishes the queued events (needs ``EventPublisher.merge_object_context``) and clears the queue."""
        if self._publisher is None:
            raise RuntimeError(
                "This aggregate isn't connected to an event bus: wrap it with EventPublisher.merge_object_context()."
            )
        events, self._uncommitted = self._uncommitted, []
        await self._publisher.publish_all(events)

    def uncommit(self) -> None:
        self._uncommitted.clear()


class EventPublisher:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus

    def merge_object_context(self, aggregate: AggregateRoot) -> AggregateRoot:
        aggregate._publisher = self.event_bus  # noqa: SLF001
        return aggregate

    def merge_class_context(self, aggregate_class: type[AggregateRoot]) -> type[AggregateRoot]:
        """A subclass whose instances are connected to the bus from construction."""
        bus = self.event_bus

        class Connected(aggregate_class):  # type: ignore[valid-type, misc]
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                self._publisher = bus

        Connected.__name__ = aggregate_class.__name__
        return Connected
