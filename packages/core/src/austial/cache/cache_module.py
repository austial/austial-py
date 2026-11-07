"""``CacheModule.register(...)`` -- mirrors ``CacheModule.register()`` from ``@nestjs/cache-manager``."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from austial.cache.cache_interceptor import CacheInterceptor
from austial.cache.cache_service import CACHE_OPTIONS, CacheOptions, CacheService
from austial.cache.store import CacheStore
from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule


@Module()
class CacheModule:
    """Import ``CacheModule.register()`` once; ``CacheService`` and ``CacheInterceptor`` are then
    injectable everywhere (the container is application-wide)."""

    @staticmethod
    def register(
        *,
        ttl: float | None = 5.0,
        max_items: int = 1000,
        store: CacheStore | None = None,
    ) -> DynamicModule:
        options = CacheOptions(ttl=ttl, max_items=max_items, store=store)
        return CacheModule._build([{"provide": CACHE_OPTIONS, "useValue": options}], [])

    @staticmethod
    def register_async(
        *,
        use_factory: Callable[..., CacheOptions],
        inject: Sequence[Any] = (),
        imports: Sequence[Any] = (),
    ) -> DynamicModule:
        provider = {"provide": CACHE_OPTIONS, "useFactory": use_factory, "inject": list(inject)}
        return CacheModule._build([provider], list(imports))

    @staticmethod
    def _build(options_providers: list[Any], imports: list[Any]) -> DynamicModule:
        return DynamicModule(
            module=CacheModule,
            imports=imports,
            providers=[*options_providers, CacheService, CacheInterceptor],
            exports=[CacheService, CacheInterceptor],
        )
