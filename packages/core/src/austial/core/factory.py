"""``AustialFactory`` -- mirrors ``NestFactory``."""

from __future__ import annotations

from fastapi import FastAPI

from austial.common.middleware.base import MiddlewareBinding, MiddlewareConsumer
from austial.core.app import AustialApplication
from austial.core.container import Container
from austial.core.module_scanner import scan_module


class AustialFactory:
    @staticmethod
    def create(
        root_module: type,
        *,
        title: str = "Austial",
        version: str = "0.1.0",
        description: str = "Built with the Austial framework.",
    ) -> AustialApplication:
        container = Container()
        scan_result = scan_module(root_module, container)

        fastapi_app = FastAPI(title=title, version=version, description=description)

        middleware_bindings: list[MiddlewareBinding] = []
        for module_cls in scan_result.modules:
            configure = getattr(module_cls, "configure", None)
            if configure is None:
                continue
            module_instance = container.resolve(module_cls)
            consumer = MiddlewareConsumer()
            module_instance.configure(consumer)
            resolved_bindings = []
            for binding in consumer.bindings:
                resolved_middlewares = [
                    container.resolve(mw) if isinstance(mw, type) else mw for mw in binding.middlewares
                ]
                resolved_bindings.append(MiddlewareBinding(middlewares=resolved_middlewares, routes=binding.routes))
            middleware_bindings.extend(resolved_bindings)

        return AustialApplication(container, fastapi_app, scan_result.controllers, middleware_bindings)
