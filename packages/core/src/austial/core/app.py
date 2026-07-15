"""``AustialApplication`` -- mirrors the object returned by
``NestFactory.create()``. Wraps a real FastAPI/Starlette app so it's a drop-in
ASGI target (``uvicorn src.main:app``) *and* offers Nest's programmatic API
(``app.listen()``, ``app.use_global_pipes()``, ...)."""

from __future__ import annotations

from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from austial.common.exceptions.http_exceptions import BadRequestException
from austial.common.filters.all_exceptions_filter import AllExceptionsFilter
from austial.common.logger import Logger
from austial.core.container import Container
from austial.core.exception_dispatch import dispatch_exception
from austial.core.router_builder import RouterBuilder

_logger = Logger("NestApplication")


class AustialApplication:
    def __init__(self, container: Container, fastapi_app: FastAPI, controllers: list, middleware_bindings: list):
        self._container = container
        self._fastapi_app = fastapi_app
        self._controllers = controllers
        self._middleware_bindings = middleware_bindings

        self._global_guards: list = []
        self._global_pipes: list = []
        self._global_interceptors: list = []
        self._global_filters: list = []
        self._routes_built = False

        self._install_fallback_exception_handlers()
        self._install_middleware()

    # -- Nest-shaped configuration API ------------------------------------------------
    def use_global_pipes(self, *pipes: Any) -> AustialApplication:
        self._global_pipes.extend(pipes)
        return self

    def use_global_guards(self, *guards: Any) -> AustialApplication:
        self._global_guards.extend(guards)
        return self

    def use_global_interceptors(self, *interceptors: Any) -> AustialApplication:
        self._global_interceptors.extend(interceptors)
        return self

    def use_global_filters(self, *filters: Any) -> AustialApplication:
        self._global_filters.extend(filters)
        return self

    def enable_cors(self, **kwargs: Any) -> AustialApplication:
        defaults = dict(allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)
        defaults.update(kwargs)
        self._fastapi_app.add_middleware(CORSMiddleware, **defaults)  # type: ignore[arg-type]
        return self

    def get(self, token: Any) -> Any:
        """Fetches a resolved provider straight out of the DI container,
        mirroring Nest's ``app.get(Token)``."""
        return self._container.resolve(token)

    def get_http_adapter(self) -> FastAPI:
        """Returns the underlying FastAPI instance, mirroring Nest's
        ``app.getHttpAdapter().getInstance()``."""
        return self._fastapi_app

    # -- lifecycle ---------------------------------------------------------------------
    async def init(self) -> AustialApplication:
        """Builds routes without starting a server -- mirrors Nest's
        ``await app.init()``, the entry point ``@nestjs/testing`` e2e tests use
        alongside ``request(app.getHttpServer())``."""
        self._build_routes()
        return self

    def _build_routes(self) -> None:
        if self._routes_built:
            return
        builder = RouterBuilder(
            self._container,
            global_guards=self._global_guards,
            global_pipes=self._global_pipes,
            global_interceptors=self._global_interceptors,
            global_filters=self._global_filters,
        )
        router = builder.build(self._controllers)
        self._fastapi_app.include_router(router)
        self._routes_built = True

    def _install_fallback_exception_handlers(self) -> None:
        async def handle_validation_error(request: Request, exc: RequestValidationError) -> Response:
            converted = BadRequestException({"message": exc.errors(), "error": "Bad Request"})
            filters = self._global_filters or [AllExceptionsFilter()]
            return await dispatch_exception(converted, request, filters)

        async def handle_uncaught(request: Request, exc: Exception) -> Response:
            filters = self._global_filters or [AllExceptionsFilter()]
            return await dispatch_exception(exc, request, filters)

        self._fastapi_app.add_exception_handler(RequestValidationError, handle_validation_error)  # type: ignore[arg-type]
        self._fastapi_app.add_exception_handler(Exception, handle_uncaught)

    def _install_middleware(self) -> None:
        if not self._middleware_bindings:
            return
        bindings = self._middleware_bindings

        class _MiddlewareDispatcher(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                applicable = [b for b in bindings if b.matches(request.url.path)]
                if not applicable:
                    return await call_next(request)

                chain = call_next

                def make_step(mw_instance, downstream):
                    async def step(req: Request):
                        return await mw_instance.use(req, lambda: downstream(req))

                    return step

                for binding in reversed(applicable):
                    for mw_instance in reversed(binding.middlewares):
                        chain = make_step(mw_instance, chain)

                return await chain(request)

        self._fastapi_app.add_middleware(_MiddlewareDispatcher)

    async def listen(self, port: int = 8000, host: str = "0.0.0.0") -> None:
        """Boots an ASGI server in-process, mirroring Nest's ``await app.listen(3000)``."""
        await self.init()
        self._print_startup_banner(port)
        config = uvicorn.Config(self._fastapi_app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
        await server.serve()

    def _print_startup_banner(self, port: int) -> None:
        _logger.log("Starting Austial application...", context="NestFactory")
        _logger.log("AppModule dependencies initialized", context="InstanceLoader")
        _logger.log(f"Austial application successfully started on port {port}", context="NestApplication")

    # -- ASGI passthrough, so `uvicorn src.main:app` works too --------------------------
    async def __call__(self, scope, receive, send) -> None:
        self._build_routes()
        await self._fastapi_app(scope, receive, send)
