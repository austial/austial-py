"""``ClientProxy`` and ``ClientsModule`` -- mirror Nest's: talk to another microservice.

::

    @Module(imports=[ClientsModule.register([ClientOptions(name="MATH", port=3001)])])
    class AppModule: ...

    @Injectable()
    class Calculator:
        def __init__(self, math: ClientProxy = Inject("MATH")):
            self.math = math

        async def total(self, numbers):
            return await self.math.send({"cmd": "sum"}, numbers)
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule
from austial.microservices.factory import build_client_transport
from austial.microservices.transport import ClientOptions, ClientTransport, pattern_key


class ClientProxy:
    def __init__(self, options: ClientOptions, transport: ClientTransport | None = None):
        self.options = options
        self.transport = transport or build_client_transport(options)

    async def connect(self) -> None:
        await self.transport.connect()

    async def send(self, pattern: Any, data: Any = None, *, timeout: float | None = None) -> Any:
        """Request-response: returns the handler's result, raises ``RpcError`` if it failed or
        ``asyncio.TimeoutError`` if nothing answered in ``timeout`` seconds (default: the client's)."""
        wait = timeout if timeout is not None else self.options.timeout
        return await asyncio.wait_for(self.transport.request(pattern_key(pattern), data), wait)

    async def emit(self, pattern: Any, data: Any = None) -> None:
        """Fire-and-forget event."""
        await self.transport.emit(pattern_key(pattern), data)

    def get_service(self, name: str) -> Any:
        """Protobuf gRPC only: a ``.proto`` service client, e.g. ``get_service("HeroService").find_one({})``."""
        getter = getattr(self.transport, "get_service", None)
        if getter is None:
            raise TypeError("get_service() needs Transport.GRPC with extra={'proto_path': ...}")
        return getter(name)

    async def close(self) -> None:
        await self.transport.close()

    # lifecycle: connect when the app initialises, close when it shuts down
    async def on_module_init(self) -> None:
        await self.connect()

    async def on_module_destroy(self) -> None:
        await self.close()


@Module()
class ClientsModule:
    @staticmethod
    def register(clients: Sequence[ClientOptions]) -> DynamicModule:
        """Registers one :class:`ClientProxy` per entry, injectable as ``Inject(options.name)``."""
        providers = [{"provide": c.name, "useValue": ClientProxy(c)} for c in clients]
        return DynamicModule(module=ClientsModule, providers=providers, exports=[c.name for c in clients])
