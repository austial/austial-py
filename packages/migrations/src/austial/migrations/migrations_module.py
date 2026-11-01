"""``MigrationsModule.for_root(...)`` -- registers :class:`MigrationRunner` in the DI
container.

The product typically also passes a URL or engine + metadata so the container can hand
back a ready-to-use runner; if only ``config`` is provided, the module still registers
``MigrationsConfig`` on its own so a downstream module can construct the runner with
lazily-resolved values.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule
from austial.migrations.config import MigrationsConfig
from austial.migrations.migration_runner import MigrationRunner


@Module()
class MigrationsModule:
    """Import via ``MigrationsModule.for_root(config, url=..., metadata=...)`` in
    ``AppModule``'s ``imports=[...]``. Registered ``@Global`` by default so any module
    can inject ``MigrationRunner`` or ``MigrationsConfig``.
    """

    @staticmethod
    def for_root(
        config: MigrationsConfig | None = None,
        *,
        url: str | None = None,
        engine: sa.Engine | None = None,
        metadata: sa.MetaData | None = None,
        is_global: bool = True,
    ) -> DynamicModule:
        cfg = config or MigrationsConfig()
        providers: list[Any] = [{"provide": MigrationsConfig, "useValue": cfg}]
        exports: list[Any] = [MigrationsConfig]

        source: sa.Engine | str | None = engine or url
        if source is not None:
            runner = MigrationRunner(source, cfg, metadata=metadata)
            providers.append({"provide": MigrationRunner, "useValue": runner})
            exports.append(MigrationRunner)

        return DynamicModule(
            module=MigrationsModule,
            providers=providers,
            exports=exports,
        )
