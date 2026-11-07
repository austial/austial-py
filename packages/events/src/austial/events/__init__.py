"""``austial.events`` -- event emitter, mirrors ``@nestjs/event-emitter``.

from austial.events import EventEmitterModule, EventEmitter, OnEvent
"""

from austial.events.emitter import EventEmitter, EventEmitterOptions
from austial.events.events_module import EventEmitterModule
from austial.events.on_event import OnEvent, OnEventSpec
from austial.events.subscribers_loader import EventSubscribersLoader

__all__ = [
    "EventEmitter",
    "EventEmitterModule",
    "EventEmitterOptions",
    "EventSubscribersLoader",
    "OnEvent",
    "OnEventSpec",
]
