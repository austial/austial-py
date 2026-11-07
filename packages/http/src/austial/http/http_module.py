"""``HttpModule.register(...)`` -- mirrors ``HttpModule.register()`` from ``@nestjs/axios``."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule
from austial.http.http_service import HTTP_OPTIONS, HttpModuleOptions, HttpService


@Module()
class HttpModule:
    @staticmethod
    def register(**options: Any) -> DynamicModule:
        """``HttpModule.register(base_url="https://api.example.com", timeout=3, retries=2)``; see
        :class:`HttpModuleOptions` for every option."""
        return HttpModule._build([{"provide": HTTP_OPTIONS, "useValue": HttpModuleOptions(**options)}], [])

    @staticmethod
    def register_async(
        *,
        use_factory: Callable[..., HttpModuleOptions],
        inject: Sequence[Any] = (),
        imports: Sequence[Any] = (),
    ) -> DynamicModule:
        provider = {"provide": HTTP_OPTIONS, "useFactory": use_factory, "inject": list(inject)}
        return HttpModule._build([provider], list(imports))

    @staticmethod
    def _build(options_providers: list[Any], imports: list[Any]) -> DynamicModule:
        return DynamicModule(
            module=HttpModule, imports=imports, providers=[*options_providers, HttpService], exports=[HttpService]
        )
