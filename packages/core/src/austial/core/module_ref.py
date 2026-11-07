"""``ModuleRef`` -- mirrors Nest's ``ModuleRef``: look providers up (or build classes) at
runtime instead of through the constructor. Injectable like any provider::

    @Injectable()
    class Dispatcher:
        def __init__(self, module_ref: ModuleRef):
            self.module_ref = module_ref

        def handler_for(self, kind: str):
            return self.module_ref.get(HANDLERS[kind])

Austial has one application-wide container (module ``exports`` aren't enforced as visibility
boundaries), so Nest's ``strict`` option has nothing to switch and isn't offered.
"""

from __future__ import annotations

from typing import Any

from austial.core.request_context import ContextId, use_context


class ModuleRef:
    def __init__(self, container: Any) -> None:
        self._container = container

    def get(self, token: Any) -> Any:
        """The provider registered under ``token`` (the singleton, for default scope).
        Request-scoped providers can't be fetched this way -- use :meth:`resolve`."""
        return self._container.resolve(token)

    def resolve(self, token: Any, context_id: ContextId | None = None) -> Any:
        """Resolves a provider of any scope. Request-scoped (or request-dependent) providers
        are built inside ``context_id`` -- pass the same :class:`ContextId` twice to get the same
        instance twice; omit it to get a fresh dependency tree each call."""
        with use_context(context_id or ContextId()):
            return self._container.resolve(token)

    def create(self, cls: type) -> Any:
        """Builds ``cls`` with its constructor dependencies injected, without registering or
        caching it -- mirrors ``moduleRef.create(Class)``."""
        return self._container.create_instance(cls)

    def has(self, token: Any) -> bool:
        return self._container.has(token)
