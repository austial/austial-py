"""``@OnEvent`` -- mirrors Nest's: declare a provider method as an event handler.

::

    @Injectable()
    class Notifications:
        @OnEvent("order.created")
        async def send_receipt(self, order: Order) -> None: ...

        @OnEvent("order.*", prepend=True)
        def audit(self, order: Order) -> None: ...

Handlers are wired when the application bootstraps (see ``EventEmitterModule``). Stack several
``@OnEvent`` decorators, or pass a list, to listen to more than one event.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from austial.core.metadata import get_metadata, set_metadata

ON_EVENT_METADATA = "austial:on_event"


@dataclass(frozen=True)
class OnEventSpec:
    event: str
    prepend: bool = False
    once: bool = False
    suppress_errors: bool | None = None  # None: the module's default


def OnEvent(  # noqa: N802
    event: str | Sequence[str],
    *,
    prepend: bool = False,
    once: bool = False,
    suppress_errors: bool | None = None,
) -> Callable:
    events = [event] if isinstance(event, str) else list(event)

    def decorator(fn):
        existing = list(get_metadata(ON_EVENT_METADATA, fn, []))
        specs = [OnEventSpec(e, prepend, once, suppress_errors) for e in events]
        set_metadata(ON_EVENT_METADATA, existing + specs)(fn)
        return fn

    return decorator
