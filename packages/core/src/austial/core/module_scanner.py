"""Walks the ``@Module`` import graph from the root ``AppModule``, registering
every provider/controller into the DI :class:`~austial.core.container.Container`
and collecting the flat list of controllers + modules for the router builder
and the middleware system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from austial.core.container import Container
from austial.core.dynamic_module import DynamicModule
from austial.core.metadata import MODULE_METADATA, get_metadata


@dataclass
class ScanResult:
    controllers: list = field(default_factory=list)
    modules: list = field(default_factory=list)


def scan_module(root_module: type, container: Container) -> ScanResult:
    visited: set[type] = set()
    controllers: list = []
    modules_in_order: list = []

    def visit(entry: Any) -> None:
        if isinstance(entry, DynamicModule):
            for provider in entry.providers:
                container.register(provider)
            for controller in entry.controllers:
                container.register(controller)
                controllers.append(controller)
            for imported in entry.imports:
                visit(imported)
            if entry.module is not None:
                visit(entry.module)
            return

        module_cls = entry
        if module_cls in visited:
            return
        visited.add(module_cls)

        metadata = get_metadata(MODULE_METADATA, module_cls)
        if metadata is None:
            raise TypeError(f"{module_cls!r} is not decorated with @Module(...)")

        for imported in metadata.imports:
            visit(imported)

        for provider in metadata.providers:
            container.register(provider)

        for controller in metadata.controllers:
            container.register(controller)
            controllers.append(controller)

        modules_in_order.append(module_cls)

    visit(root_module)
    return ScanResult(controllers=controllers, modules=modules_in_order)
