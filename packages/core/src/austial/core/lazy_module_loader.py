"""``LazyModuleLoader`` -- mirrors Nest's: register a module *after* startup, on first use,
so rarely-needed features (and their imports) don't slow cold starts::

    module_ref = await self.lazy_loader.load(lambda: ReportsModule)
    reports = module_ref.get(ReportsService)

Lazy modules join the application's single container, so -- like everything else in Austial --
their providers become resolvable application-wide once loaded. Their controllers are *not*
routed (Nest doesn't route them either). Lifecycle hooks of a lazily loaded module run on load
if the application is already initialised.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from austial.core.container import Container
from austial.core.forward_ref import unwrap
from austial.core.module_ref import ModuleRef
from austial.core.module_scanner import scan_module


class LazyModuleLoader:
    def __init__(self, container: Container, module_ref: ModuleRef):
        self._container = container
        self._module_ref = module_ref
        self._loaded: set[Any] = set(self._already_scanned())

    def _already_scanned(self) -> list:
        return [record.module for record in self._container.module_records if record.module is not None]

    async def load(self, loader: Callable[[], Any] | type) -> ModuleRef:
        """``loader`` is the module itself, a (dynamic) module value, or a callable (sync or
        async) returning one -- the callable form lets you defer the *import*."""
        target = loader
        if callable(loader) and not isinstance(loader, type):
            target = loader()
            if inspect.isawaitable(target):
                target = await target
        target = unwrap(target)
        scan = scan_module(target, self._container, visited=self._loaded)
        if self._container.lifecycle.started and scan.records:
            await self._container.lifecycle.run_init(scan.records)
        return self._module_ref
