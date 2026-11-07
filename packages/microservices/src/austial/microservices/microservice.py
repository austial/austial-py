"""Standalone and hybrid microservices."""

from __future__ import annotations

from typing import Any

from austial.core.application_context import AustialApplicationContext
from austial.core.container import Container
from austial.core.discovery import DiscoveryService
from austial.core.module_ref import ModuleRef
from austial.core.module_scanner import scan_module
from austial.microservices.factory import build_server_transport
from austial.microservices.server import HandlerRegistry, MicroserviceServer
from austial.microservices.transport import MicroserviceOptions


def build_server(container: Container, options: MicroserviceOptions) -> MicroserviceServer:
    registry = HandlerRegistry(container.resolve(DiscoveryService), container.resolve(ModuleRef))
    return MicroserviceServer(build_server_transport(options), registry)


class MicroserviceApplication(AustialApplicationContext):
    """What ``create_microservice`` returns: a DI context plus a transport server.

    ``await ms.listen()`` initialises the app (hooks, async providers) and starts the transport;
    ``await ms.close()`` stops it and runs the shutdown hooks.
    """

    def __init__(self, container: Container, options: MicroserviceOptions):
        super().__init__(container)
        self.options = options
        self.server = build_server(container, options)

    async def listen(self) -> None:
        await self.init()
        await self.server.start()

    async def close(self, signal: str | None = None) -> None:
        await self.server.stop()
        await super().close(signal)


def create_microservice(root_module: type, options: MicroserviceOptions) -> MicroserviceApplication:
    """Mirrors ``NestFactory.createMicroservice()``: a message-driven app with no HTTP server."""
    container = Container()
    scan_module(root_module, container)
    return MicroserviceApplication(container, options)


def attach_microservice(app: Any, options: MicroserviceOptions) -> MicroserviceServer:
    """Hybrid app: serve ``options`` from the same application as HTTP. Used by ``app.connect_microservice()``."""
    return build_server(app._container, options)  # noqa: SLF001
