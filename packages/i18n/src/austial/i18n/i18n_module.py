"""``I18nModule.for_root(config)`` -- wires the loader, service, request-scoped
context and locale-detecting middleware into the DI container.

Global by default so any module can inject ``I18nService`` / ``I18nContext``
without re-importing the module.
"""

from __future__ import annotations

from typing import Any

from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule
from austial.i18n.config import I18nConfig
from austial.i18n.i18n_context import I18nContext
from austial.i18n.i18n_service import I18nService
from austial.i18n.locale_middleware import LocaleMiddleware


@Module()
class I18nModule:
    """Import via ``I18nModule.for_root(I18nConfig(...))`` in ``AppModule``'s
    ``imports=[...]``."""

    @staticmethod
    def for_root(config: I18nConfig, *, is_global: bool = True) -> DynamicModule:
        service = I18nService(config)
        middleware = LocaleMiddleware(service, config)
        providers: list[Any] = [
            {"provide": I18nConfig, "useValue": config},
            {"provide": I18nService, "useValue": service},
            {"provide": LocaleMiddleware, "useValue": middleware},
            I18nContext,
        ]
        return DynamicModule(
            module=I18nModule,
            providers=providers,
            exports=[I18nConfig, I18nService, I18nContext, LocaleMiddleware],
        )
