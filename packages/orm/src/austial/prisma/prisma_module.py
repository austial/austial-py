"""``PrismaModule`` -- connect a Prisma client with the application's lifecycle, mirrors Nest's Prisma recipe.

Prisma's Python client is generated inside your project (``prisma generate`` -> ``from prisma import Prisma``), so this
module is deliberately client-agnostic: give it the class (or an instance) and it connects on init and disconnects on
shutdown. Anything with async ``connect()`` / ``disconnect()`` works.

::

    from prisma import Prisma

    @Module(imports=[PrismaModule.for_root(Prisma)])
    class AppModule: ...

    @Injectable()
    class CatsService:
        def __init__(self, db: Prisma):                 # injected by its own class
            self.db = db

        async def find_all(self):
            return await self.db.cat.find_many()
"""

from __future__ import annotations

from typing import Any

from austial.common.decorators.injectable import Inject
from austial.common.decorators.modules import Module
from austial.common.logger import Logger
from austial.core.dynamic_module import DynamicModule

_logger = Logger("PrismaModule")


@Module()
class PrismaModule:
    @staticmethod
    def for_root(client: Any, *, connect: bool = True, **client_kwargs: Any) -> DynamicModule:
        """``client`` is the generated client **class** (built with ``client_kwargs``) or an instance. It is
        injectable by its class. ``connect=False`` leaves ``connect()`` to you (Prisma also connects lazily)."""
        is_class = isinstance(client, type)
        token = client if is_class else type(client)
        provider = (
            {"provide": token, "useFactory": lambda: client(**client_kwargs), "inject": []}
            if is_class
            else {"provide": token, "useValue": client}
        )

        class PrismaLifecycle:
            def __init__(self, prisma: Any = Inject(token)):
                self.prisma = prisma

            async def on_module_init(self) -> None:
                if connect:
                    await self.prisma.connect()
                    _logger.log("Prisma client connected")

            async def on_module_destroy(self) -> None:
                is_connected = getattr(self.prisma, "is_connected", None)
                if is_connected is None or is_connected():
                    await self.prisma.disconnect()

        return DynamicModule(module=PrismaModule, providers=[provider, PrismaLifecycle], exports=[token])
