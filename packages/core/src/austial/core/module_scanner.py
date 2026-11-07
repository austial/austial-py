"""Walks the ``@Module`` import graph from the root ``AppModule``, registering
every provider/controller into the DI :class:`~austial.core.container.Container`
and collecting the flat list of controllers + modules for the router builder
and the middleware system.

Every module also leaves a :class:`~austial.core.container.ModuleRecord` on the container
(dependencies first), which is what lifecycle hooks and ``DiscoveryService`` iterate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from austial.core.container import Container, ModuleRecord
from austial.core.dynamic_module import DynamicModule
from austial.core.forward_ref import unwrap
from austial.core.metadata import MODULE_METADATA, get_metadata


@dataclass
class ScanResult:
    controllers: list = field(default_factory=list)
    modules: list = field(default_factory=list)
    records: list = field(default_factory=list)  # ModuleRecords created by *this* scan


def _token_of(provider: Any) -> Any:
    return unwrap(provider["provide"]) if isinstance(provider, dict) else unwrap(provider)


def scan_module(root_module: type, container: Container, *, visited: set | None = None) -> ScanResult:
    """Registers ``root_module`` and everything it imports. ``visited`` lets a caller
    (``LazyModuleLoader``) skip modules an earlier scan already registered."""
    visited = set() if visited is None else visited
    controllers: list = []
    modules_in_order: list = []
    records: dict[Any, ModuleRecord] = {}
    ordered_records: list[ModuleRecord] = []

    def record_for(module_cls: type | None) -> ModuleRecord:
        key = module_cls if module_cls is not None else object()
        if key not in records:
            records[key] = ModuleRecord(module=module_cls)
            ordered_records.append(records[key])
        return records[key]

    def add_providers(record: ModuleRecord, providers: list) -> None:
        for provider in providers:
            container.register(provider)
            record.providers.append(_token_of(provider))

    def add_controllers(record: ModuleRecord, module_controllers: list) -> None:
        for controller in module_controllers:
            controller = unwrap(controller)
            container.register_controller(controller)
            record.controllers.append(controller)
            controllers.append(controller)

    def visit(entry: Any) -> None:
        entry = unwrap(entry)
        dynamic = entry if isinstance(entry, DynamicModule) else None
        module_cls = dynamic.module if dynamic is not None else entry

        if dynamic is not None:
            for imported in dynamic.imports:
                visit(imported)

        static_metadata = None
        first_visit = module_cls is not None and module_cls not in visited
        if first_visit:
            visited.add(module_cls)
            static_metadata = get_metadata(MODULE_METADATA, module_cls)
            if static_metadata is None:
                raise TypeError(f"{module_cls!r} is not decorated with @Module(...)")
            for imported in static_metadata.imports:
                visit(imported)

        record = record_for(module_cls)
        if static_metadata is not None:
            add_providers(record, static_metadata.providers)
            add_controllers(record, static_metadata.controllers)
        if dynamic is not None:
            add_providers(record, dynamic.providers)
            add_controllers(record, dynamic.controllers)
        if first_visit:
            modules_in_order.append(module_cls)

    visit(root_module)
    container.module_records.extend(ordered_records)
    return ScanResult(controllers=controllers, modules=modules_in_order, records=ordered_records)
