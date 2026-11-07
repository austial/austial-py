"""``AustialApplication`` -- mirrors the object returned by
``NestFactory.create()``. Wraps a real FastAPI/Starlette app so it's a drop-in
ASGI target (``uvicorn src.main:app``) *and* offers Nest's programmatic API
(``app.listen()``, ``app.use_global_pipes()``, ...)."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from austial.common.enums import VersioningType
from austial.common.exceptions.http_exceptions import BadRequestException
from austial.common.filters.all_exceptions_filter import AllExceptionsFilter
from austial.common.logger import Logger
from austial.core.application_context import AustialApplicationContext
from austial.core.container import Container
from austial.core.exception_dispatch import dispatch_exception
from austial.core.http_adapter_host import HttpAdapterHost
from austial.core.router_builder import RouterBuilder
from austial.core.routing import GlobalPrefix, RouteInfo, VersioningOptions

_logger = Logger("NestApplication")


class AustialApplication(AustialApplicationContext):
    _owns_signals = False  # the ASGI server handles signals and drives shutdown via lifespan

    def __init__(self, container: Container, fastapi_app: FastAPI, controllers: list, middleware_bindings: list):
        super().__init__(container)
        self._fastapi_app = fastapi_app
        self._controllers = controllers
        self._middleware_bindings = middleware_bindings

        self._global_guards: list = []
        self._global_pipes: list = []
        self._global_interceptors: list = []
        self._global_filters: list = []
        self._routes_built = False
        self._global_prefix: GlobalPrefix | None = None
        self._versioning: VersioningOptions | None = None
        self._static_mounts: list[tuple[str, str, dict[str, Any]]] = []
        self._views_dir: str | None = None
        self._microservices: list[Any] = []
        self._url: str | None = None
        self._server: Any = None

        self._install_fallback_exception_handlers()
        self._install_middleware()
        self._install_lifespan()
        container.resolve(HttpAdapterHost).http_adapter = fastapi_app

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

    def set_global_prefix(self, prefix: str, *, exclude: list[str | RouteInfo] | None = None) -> AustialApplication:
        """Prefixes every route (``/api/cats``), except those in ``exclude`` -- plain paths or
        ``RouteInfo(path, method)``. Mirrors Nest's ``app.setGlobalPrefix('api', {exclude})``.
        Call before routes are built (before ``init()`` / the first request)."""
        self._ensure_routes_not_built("set_global_prefix")
        self._global_prefix = GlobalPrefix(prefix=prefix, exclude=exclude or [])
        return self

    def enable_versioning(
        self,
        type: VersioningType = VersioningType.URI,  # noqa: A002 - mirrors Nest's `type` option
        *,
        prefix: str | bool = "v",
        header: str | None = None,
        key: str = "v=",
        default_version: str | list[str] | None = None,
        extractor: Any = None,
    ) -> AustialApplication:
        """Turns on API versioning, mirrors ``app.enableVersioning({...})``. ``type`` picks where
        the version lives: the URL (``/v1/cats``), a ``header`` (``X-API-Version: 1``), the ``Accept``
        header's ``key`` parameter (``application/json;v=1``) or whatever ``extractor(request)``
        returns. Pin routes with ``@Controller(version=...)`` / ``@Version(...)``;
        ``default_version`` covers routes that name none."""
        self._ensure_routes_not_built("enable_versioning")
        if type == VersioningType.HEADER and not header:
            raise ValueError("enable_versioning(HEADER) needs header=")
        if type == VersioningType.CUSTOM and extractor is None:
            raise ValueError("enable_versioning(CUSTOM) needs extractor=")
        self._versioning = VersioningOptions(
            type=type, prefix=prefix, header=header, key=key, default_version=default_version, extractor=extractor
        )
        return self

    def connect_microservice(self, options: Any, *, auto_start: bool = True) -> AustialApplication:
        """Makes this a *hybrid* application: besides HTTP it also serves ``@MessagePattern``/``@EventPattern``
        handlers over ``options`` (an ``austial.microservices.MicroserviceOptions``). With ``auto_start`` (default)
        the transport starts and stops with the application; otherwise call ``await start_all_microservices()``."""
        try:
            from austial.microservices import attach_microservice
        except ImportError as exc:  # pragma: no cover - austial-microservices ships with the umbrella package
            raise RuntimeError("connect_microservice needs the austial-microservices package") from exc
        server = attach_microservice(self, options)
        self._microservices.append(server)
        if auto_start:
            self._extensions.append(server)
        return self

    async def start_all_microservices(self) -> None:
        for server in self._microservices:
            await server.start()

    def use_logger(self, logger: Any) -> AustialApplication:
        """Replaces the framework's logger (a ``LoggerService``, a list of levels, or ``False``) and flushes
        any output held back by ``buffer_logs=True``. Mirrors ``app.useLogger()``."""
        Logger.override_logger(logger)
        Logger.flush()
        return self

    def set_base_views_dir(self, directory: str) -> AustialApplication:
        """Where ``@Render("name.html")`` finds its Jinja2 templates, mirrors ``app.setBaseViewsDir()``."""
        self._ensure_routes_not_built("set_base_views_dir")
        self._views_dir = directory
        return self

    def use_static_assets(self, directory: str, *, prefix: str = "/", **options: Any) -> AustialApplication:
        """Serves the files in ``directory`` under ``prefix`` (``html=True`` serves ``index.html``),
        mirrors Nest's ``app.useStaticAssets``. Mounted *after* the API routes, so those win."""
        self._static_mounts.append((directory, prefix, options))
        return self

    def use_compression(self, *, minimum_size: int = 500, compresslevel: int = 9) -> AustialApplication:
        """gzip-compresses responses of at least ``minimum_size`` bytes, for clients that accept it."""
        from starlette.middleware.gzip import GZipMiddleware

        self._fastapi_app.add_middleware(GZipMiddleware, minimum_size=minimum_size, compresslevel=compresslevel)
        return self

    def set_trust_proxy(self, trusted_hosts: str | list[str] = "*") -> AustialApplication:
        """Trusts ``X-Forwarded-For`` / ``X-Forwarded-Proto`` from ``trusted_hosts``, so the
        client IP (``Ip()``, ``request.client``) and scheme are the real ones behind a reverse proxy."""
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

        self._fastapi_app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_hosts)
        return self

    def use(self, middleware: Any, **options: Any) -> AustialApplication:
        """Adds any ASGI middleware class (``SessionMiddleware``, ``TrustedHostMiddleware``...),
        mirrors Nest's ``app.use()``."""
        self._fastapi_app.add_middleware(middleware, **options)
        return self

    def _ensure_routes_not_built(self, method: str) -> None:
        if self._routes_built:
            raise RuntimeError(f"app.{method}() must be called before the application is initialised")

    def get_http_adapter(self) -> FastAPI:
        """Returns the underlying FastAPI instance, mirroring Nest's
        ``app.getHttpAdapter().getInstance()``."""
        return self._fastapi_app

    # -- lifecycle ---------------------------------------------------------------------
    async def init(self) -> AustialApplication:
        """Builds routes and runs the ``on_module_init`` / ``on_application_bootstrap`` hooks
        without starting a server -- mirrors Nest's ``await app.init()``, the entry point
        ``@nestjs/testing`` e2e tests use alongside ``request(app.getHttpServer())``."""
        Logger.flush()
        await self._container.init_async_providers()  # controllers may depend on async providers
        self._build_routes()
        await super().init()
        return self

    def _install_lifespan(self) -> None:
        """Runs the lifecycle hooks from the ASGI lifespan: startup hooks after the FastAPI
        ``on_event("startup")`` handlers (so e.g. a ``DataSource`` is ready), shutdown hooks before
        the ``"shutdown"`` ones."""
        router = self._fastapi_app.router
        wrapped = router.lifespan_context

        @contextlib.asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[Any]:
            async with wrapped(app) as state:
                await AustialApplicationContext.init(self)
                try:
                    yield state
                finally:
                    await self.close()

        router.lifespan_context = lifespan

    def _build_routes(self) -> None:
        if self._routes_built:
            return
        builder = RouterBuilder(
            self._container,
            global_guards=self._global_guards,
            global_pipes=self._global_pipes,
            global_interceptors=self._global_interceptors,
            global_filters=self._global_filters,
            global_prefix=self._global_prefix,
            versioning=self._versioning,
            views_dir=self._views_dir,
        )
        router = builder.build(self._controllers)
        self._fastapi_app.include_router(router)
        for directory, prefix, options in self._static_mounts:
            from starlette.staticfiles import StaticFiles

            self._fastapi_app.mount(prefix.rstrip("/") or "/", StaticFiles(directory=directory, **options))
        self._routes_built = True

    def _install_fallback_exception_handlers(self) -> None:
        async def handle_validation_error(request: Request, exc: RequestValidationError) -> Response:
            converted = BadRequestException({"message": jsonable_encoder(exc.errors()), "error": "Bad Request"})
            return await dispatch_exception(converted, request, self._fallback_filters())

        async def handle_uncaught(request: Request, exc: Exception) -> Response:
            return await dispatch_exception(exc, request, self._fallback_filters())

        self._fastapi_app.add_exception_handler(RequestValidationError, handle_validation_error)  # type: ignore[arg-type]
        self._fastapi_app.add_exception_handler(Exception, handle_uncaught)

    def _fallback_filters(self) -> list:
        """Filters for errors raised outside a route handler (e.g. FastAPI's own validation errors):
        ``use_global_filters`` instances, filters registered under ``APP_FILTER``, then the default
        ``AllExceptionsFilter`` so nothing escapes unrendered."""
        filters = list(self._global_filters)
        for token in self._container.global_components("filters"):
            if not self._container.is_request_bound(token):
                filters.append(self._container.resolve(token))
        filters.append(AllExceptionsFilter())
        return filters

    def _install_middleware(self) -> None:
        if not self._middleware_bindings:
            return
        bindings = self._middleware_bindings

        class _MiddlewareDispatcher(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                applicable = [b for b in bindings if b.matches(request.url.path, request.method)]
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

    def get_url(self) -> str:
        """The URL the server is listening on, e.g. ``http://127.0.0.1:8000`` -- once :meth:`listen` is running."""
        if self._url is None:
            raise RuntimeError("The application isn't listening yet: call `await app.listen(...)` first.")
        return self._url

    def get_http_server(self) -> Any:
        """The ``uvicorn.Server`` behind :meth:`listen` (``None`` before it starts)."""
        return self._server

    async def listen(self, port: int = 8000, host: str = "0.0.0.0", **uvicorn_options: Any) -> None:
        """Boots an ASGI server in-process, mirroring Nest's ``await app.listen(3000)``.

        Hands uvicorn ``self`` (the ``AustialApplication`` ASGI wrapper), not the raw
        ``FastAPI`` instance, so this entry point goes through the exact same lazy,
        lifespan-aware route-building as ``uvicorn src.main:app`` / ``austial serve``
        (see ``__call__``) -- keeping every entry point's startup ordering identical
        instead of ``listen()`` eagerly building routes here, before uvicorn's ASGI
        lifespan protocol has run any ``"startup"`` event handlers registered via
        ``get_http_adapter()``.
        """
        self._print_startup_banner(port)
        uvicorn_options.setdefault("log_level", "warning")
        config = uvicorn.Config(self, host=host, port=port, **uvicorn_options)
        scheme = "https" if config.is_ssl else "http"
        self._url = f"{scheme}://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}"  # noqa: S104
        self._server = uvicorn.Server(config)
        await self._server.serve()

    def _print_startup_banner(self, port: int) -> None:
        _logger.log("Starting Austial application...", context="NestFactory")
        _logger.log("AppModule dependencies initialized", context="InstanceLoader")
        _logger.log(f"Austial application successfully started on port {port}", context="NestApplication")

    # -- ASGI passthrough, so `uvicorn src.main:app` works too --------------------------
    async def __call__(self, scope, receive, send) -> None:
        """Handles both the ASGI "lifespan" scope (uvicorn's startup/shutdown
        handshake) and real request scopes.

        Routes -- and therefore every controller's and every global
        guard/pipe/interceptor/filter's DI dependencies -- are built lazily on the
        first *non*-lifespan scope rather than eagerly on every call (including the
        lifespan one). Building them eagerly here used to run before uvicorn's ASGI
        lifespan protocol fired any ``"startup"`` event handler registered via
        ``get_http_adapter().on_event("startup")`` (e.g. ``DataSource.initialize()``,
        the documented pattern in ``austial.orm``'s "the one manual step"), so any
        global guard/pipe/interceptor/filter with a constructor-injected dependency
        that only becomes valid post-startup (e.g. ``InjectRepository`` before the
        ``DataSource`` was initialized) crashed route-building on every boot. By the
        time the first non-lifespan scope arrives, the ASGI lifespan handshake --
        and every ``"startup"`` handler it ran -- has already completed.
        """
        if scope["type"] != "lifespan":
            self._build_routes()
        await self._fastapi_app(scope, receive, send)
