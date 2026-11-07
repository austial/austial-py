"""Runs provider lifecycle hooks (``on_module_init`` ... ``on_application_shutdown``).

Hooks are found by name on providers, controllers and module classes. Providers that define at
least one hook are instantiated eagerly so they can't be skipped; every other provider stays
lazy (instantiating *everything* at startup would trip providers that are only valid after the
ASGI startup handlers ran, e.g. a repository over a not-yet-initialised ``DataSource``).
Transient and request-scoped providers never get hooks, matching Nest.
"""

from __future__ import annotations

import inspect
from typing import Any

from austial.common.enums import Scope
from austial.common.lifecycle import (
    BEFORE_APPLICATION_SHUTDOWN,
    LIFECYCLE_HOOKS,
    ON_APPLICATION_BOOTSTRAP,
    ON_APPLICATION_SHUTDOWN,
    ON_MODULE_DESTROY,
    ON_MODULE_INIT,
)
from austial.core.container import _UNSET  # noqa: E402 - container imports this module lazily, never at import time

_SIGNAL_HOOKS = {BEFORE_APPLICATION_SHUTDOWN, ON_APPLICATION_SHUTDOWN}


def _defines_hook(obj: Any) -> bool:
    return any(callable(getattr(obj, name, None)) for name in LIFECYCLE_HOOKS)


class LifecycleManager:
    def __init__(self, container: Any) -> None:
        self._container = container
        self._called: dict[str, set[int]] = {name: set() for name in LIFECYCLE_HOOKS}
        self.started = False  # True between a completed run_init() and the next run_destroy()

    # -- target discovery -------------------------------------------------------------
    def _instance_for(self, token: Any) -> Any:
        """The hook-bearing instance behind ``token``, or ``None`` if there's nothing to call."""
        container = self._container
        definition = container._definitions.get(token)
        if definition is None or definition.scope == Scope.TRANSIENT:
            return None
        if definition.use_existing is not _UNSET:
            return None  # an alias -- the real provider is visited under its own token
        if container.is_request_bound(token):
            return None
        if token in container._singletons:
            return container._singletons[token]
        if definition.use_class is not None and _defines_hook(definition.use_class):
            return container.resolve(token)
        if definition.use_value is not _UNSET and _defines_hook(definition.use_value):
            return definition.use_value
        return None

    def _targets(self, records: list) -> list[Any]:
        seen: set[int] = set()
        targets: list[Any] = []

        def add(instance: Any) -> None:
            if instance is not None and id(instance) not in seen and _defines_hook(instance):
                seen.add(id(instance))
                targets.append(instance)

        for record in records:
            for token in [*record.providers, *record.controllers]:
                add(self._instance_for(token))
            if record.module is not None and _defines_hook(record.module):
                add(self._container.resolve(record.module))
        return targets

    # -- invocation -------------------------------------------------------------------
    async def _call(self, hook: str, targets: list[Any], signal: str | None) -> None:
        for instance in targets:
            if id(instance) in self._called[hook]:
                continue
            self._called[hook].add(id(instance))
            method = getattr(instance, hook, None)
            if not callable(method):
                continue
            result = method(signal) if hook in _SIGNAL_HOOKS and _accepts_argument(method) else method()
            if inspect.isawaitable(result):
                await result

    async def run_init(self, records: list | None = None) -> None:
        targets = self._targets(self._container.module_records if records is None else records)
        await self._call(ON_MODULE_INIT, targets, None)
        await self._call(ON_APPLICATION_BOOTSTRAP, targets, None)
        self.started = True

    async def run_destroy(self, signal: str | None = None) -> None:
        targets = list(reversed(self._targets(self._container.module_records)))
        await self._call(ON_MODULE_DESTROY, targets, signal)
        await self._call(BEFORE_APPLICATION_SHUTDOWN, targets, signal)
        await self._call(ON_APPLICATION_SHUTDOWN, targets, signal)
        self.started = False

    def reset(self) -> None:
        """Forgets which hooks already ran, so a closed application can be initialised again."""
        for called in self._called.values():
            called.clear()


def _accepts_argument(method: Any) -> bool:
    try:
        parameters = inspect.signature(method).parameters.values()
    except (TypeError, ValueError):
        return False
    accepted = (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.VAR_POSITIONAL,
    )
    return any(p.kind in accepted for p in parameters)
