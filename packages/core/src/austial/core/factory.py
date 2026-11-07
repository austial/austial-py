"""``AustialFactory`` -- mirrors ``NestFactory``."""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import FastAPI

from austial.common.logger import Logger, LoggerService
from austial.common.middleware.base import MiddlewareBinding, MiddlewareConsumer
from austial.core.app import AustialApplication
from austial.core.application_context import AustialApplicationContext
from austial.core.container import Container
from austial.core.module_scanner import scan_module


def _configure_logging(logger: LoggerService | Sequence[str] | bool | None, buffer_logs: bool) -> None:
    if buffer_logs:
        Logger.attach_buffer()
    if logger is not None:
        Logger.override_logger(logger)
        if buffer_logs:
            Logger.flush()  # the custom logger is already known: nothing left to wait for


class AustialFactory:
    @staticmethod
    def create(
        root_module: type,
        *,
        title: str = "Austial",
        version: str = "0.1.0",
        description: str = "Built with the Austial framework.",
        logger: LoggerService | Sequence[str] | bool | None = None,
        buffer_logs: bool = False,
    ) -> AustialApplication:
        """``logger`` replaces the framework's logger for the whole process: a ``LoggerService``, a list of
        levels (``["error", "warn"]``), or ``False`` to silence it. ``buffer_logs=True`` holds startup
        output until you attach a logger with ``app.use_logger(...)`` (or ``app.init()`` runs)."""
        _configure_logging(logger, buffer_logs)
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

    @staticmethod
    async def create_application_context(
        root_module: type,
        *,
        logger: LoggerService | Sequence[str] | bool | None = None,
        buffer_logs: bool = False,
    ) -> AustialApplicationContext:
        """Builds the module graph and runs the lifecycle hooks *without* an HTTP server -- for
        CLIs, workers and scripts. Mirrors ``NestFactory.createApplicationContext()``. Call
        ``await ctx.close()`` when done."""
        _configure_logging(logger, buffer_logs)
        container = Container()
        scan_module(root_module, container)
        context = AustialApplicationContext(container)
        await context.init()
        return context
