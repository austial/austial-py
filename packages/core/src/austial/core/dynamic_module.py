"""``DynamicModule`` -- mirrors Nest's dynamic module pattern
(``ConfigModule.forRoot()``, ``TypeOrmModule.forRootAsync()``, ...).

A module class exposes a classmethod (conventionally ``for_root`` /
``for_root_async`` / ``register``) that returns a ``DynamicModule`` describing
extra providers/controllers/imports/exports to merge in at that import site,
instead of (or in addition to) whatever static ``@Module(...)`` metadata the
class itself carries.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DynamicModule:
    module: type | None = None
    imports: list = field(default_factory=list)
    controllers: list = field(default_factory=list)
    providers: list = field(default_factory=list)
    exports: list = field(default_factory=list)
