"""Discovers ``@OnEvent`` handlers on providers and controllers and subscribes them to the emitter."""

from __future__ import annotations

from austial.common.logger import Logger
from austial.core.discovery import DiscoveryService
from austial.events.emitter import EventEmitter
from austial.events.on_event import ON_EVENT_METADATA

_logger = Logger("EventSubscribersLoader")


class EventSubscribersLoader:
    def __init__(self, discovery: DiscoveryService, emitter: EventEmitter):
        self.discovery = discovery
        self.emitter = emitter
        self.subscribed = 0

    def on_application_bootstrap(self) -> None:
        for controllers in (False, True):
            for wrapper, method_name, specs in self.discovery.get_methods_with_metadata(
                ON_EVENT_METADATA, controllers=controllers
            ):
                if wrapper.instance is None:
                    _logger.warn(
                        f"Skipping @OnEvent on {wrapper.name}.{method_name}: request-scoped providers can't subscribe"
                    )
                    continue
                handler = getattr(wrapper.instance, method_name)
                for spec in specs:
                    self.emitter.on(
                        spec.event,
                        handler,
                        prepend=spec.prepend,
                        once=spec.once,
                        suppress_errors=spec.suppress_errors,
                    )
                    self.subscribed += 1
