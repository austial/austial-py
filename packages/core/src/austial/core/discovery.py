"""``DiscoveryService`` -- mirrors ``@nestjs/core``'s ``DiscoveryService``: enumerate the
application's providers and controllers (optionally filtered by metadata) so a feature module
can wire itself to decorated classes/methods it finds -- exactly how ``@nestjs/schedule`` and
``@nestjs/event-emitter`` discover ``@Cron()`` / ``@OnEvent()`` handlers::

    @Injectable()
    class EventExplorer:
        def __init__(self, discovery: DiscoveryService):
            self.discovery = discovery

        def on_module_init(self):
            for wrapper, method_name, topic in self.discovery.get_methods_with_metadata(TOPIC_KEY):
                bus.subscribe(topic, getattr(wrapper.instance, method_name))
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from austial.common.enums import Scope
from austial.core.container import _UNSET, Container
from austial.core.metadata import get_metadata, has_metadata


@dataclass
class InstanceWrapper:
    """One discovered provider/controller. ``instance`` is ``None`` until the container has
    built it (providers are lazy), or for transient/request-scoped providers, which have no
    single instance. ``metatype`` is the class behind it, when there is one."""

    token: Any
    metatype: type | None
    instance: Any
    scope: Scope
    is_controller: bool = False

    @property
    def name(self) -> str:
        return getattr(self.token, "__name__", str(self.token))

    def has_metadata(self, key: str) -> bool:
        return self.metatype is not None and has_metadata(key, self.metatype)

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return get_metadata(key, self.metatype, default) if self.metatype is not None else default


class DiscoveryService:
    def __init__(self, container: Container):
        self._container = container

    def _wrappers(self, *, controllers: bool) -> list[InstanceWrapper]:
        container = self._container
        controller_tokens = set(container.controllers)
        wrappers: list[InstanceWrapper] = []
        for definition in container.definitions():
            token = definition.token
            if container.is_module(token) or token in container.internal_tokens:
                continue
            if (token in controller_tokens) != controllers:
                continue
            scoped = definition.scope != Scope.DEFAULT or container.is_request_bound(token)
            instance = None if scoped else container._singletons.get(token)
            if instance is None and definition.use_value is not _UNSET:
                instance = definition.use_value
            wrappers.append(
                InstanceWrapper(
                    token=token,
                    metatype=definition.use_class,
                    instance=instance,
                    scope=definition.scope,
                    is_controller=controllers,
                )
            )
        return wrappers

    def get_providers(self, metadata_key: str | None = None) -> list[InstanceWrapper]:
        """Every registered provider (controllers and modules excluded), optionally only those
        whose class carries ``metadata_key``."""
        found = self._wrappers(controllers=False)
        return [w for w in found if metadata_key is None or w.has_metadata(metadata_key)]

    def get_controllers(self, metadata_key: str | None = None) -> list[InstanceWrapper]:
        found = self._wrappers(controllers=True)
        return [w for w in found if metadata_key is None or w.has_metadata(metadata_key)]

    def get_methods_with_metadata(self, metadata_key: str, *, controllers: bool = False) -> list[tuple]:
        """``(wrapper, method_name, metadata_value)`` for every method of every discovered
        class that was decorated with ``set_metadata(metadata_key, ...)``. Instances are built
        on demand (singleton providers only) so ``wrapper.instance`` is usable."""
        wrappers = self.get_controllers() if controllers else self.get_providers()
        found: list[tuple] = []
        for wrapper in wrappers:
            if wrapper.metatype is None:
                continue
            for name, member in inspect.getmembers(wrapper.metatype, predicate=callable):
                if name.startswith("__") or not has_metadata(metadata_key, member):
                    continue
                if wrapper.instance is None and wrapper.scope == Scope.DEFAULT:
                    if self._container.is_request_bound(wrapper.token):
                        continue
                    wrapper.instance = self._container.resolve(wrapper.token)
                found.append((wrapper, name, get_metadata(metadata_key, member)))
        return found
