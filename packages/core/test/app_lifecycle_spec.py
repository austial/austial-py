"""Regression test for a real, 100%-reproducible production bootstrap-ordering
bug: ``AustialApplication`` used to build routes (and therefore eagerly
resolve every controller's and every global guard/pipe/interceptor/filter's DI
dependencies) *before* uvicorn's ASGI lifespan protocol ran any ``"startup"``
event handler registered via ``get_http_adapter().on_event("startup")`` -- the
documented pattern ``austial.orm``'s docs use for ``DataSource.initialize()``,
since ``austial serve``/``uvicorn src.main:app`` never call a user
``bootstrap()`` function.

Reproduced here without ``austial.orm``: a fake data-source-shaped provider
that raises exactly like ``DataSource.get_repository()`` does until its async
``initialize()`` has run, injected into a global interceptor's constructor --
the same shape as Swadely's real ``AuditInterceptor`` +
``InjectRepository(AuditLog)`` that crash-looped in production.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from austial.common.decorators.controllers import Controller, Get
from austial.common.decorators.injectable import Inject, Injectable
from austial.common.decorators.modules import Module
from austial.common.guards.base import ExecutionContext
from austial.common.interceptors.base import CallHandler, NestInterceptor
from austial.core.app import AustialApplication
from austial.core.container import Container
from austial.core.module_scanner import scan_module

_DATA_SOURCE_TOKEN = "FAKE_DATA_SOURCE"


class _FakeDataSource:
    """Stands in for ``austial.orm.DataSource``: cheap to construct at
    module-scan time, but not safe to use until its async ``initialize()`` --
    registered as a ``"startup"`` lifespan handler -- has actually run."""

    def __init__(self) -> None:
        self.initialized = False

    async def initialize(self) -> None:
        self.initialized = True

    def get_repository(self) -> str:
        if not self.initialized:
            raise RuntimeError("DataSource.initialize() must be called before use.")
        return "a-real-repository"


@Injectable()
class _AuditInterceptor(NestInterceptor):
    """Mirrors Swadely's real global ``AuditInterceptor``: eagerly resolves a
    repository-shaped dependency in its constructor."""

    def __init__(self, data_source: _FakeDataSource = Inject(_DATA_SOURCE_TOKEN)):
        self.repository = data_source.get_repository()

    async def intercept(self, context: ExecutionContext, next: CallHandler):
        return await next.handle()


@Controller("ping")
class _PingController:
    @Get()
    async def ping(self) -> dict:
        return {"ok": True}


@Module(controllers=[_PingController])
class _RootModule:
    pass


def _build_app() -> tuple[AustialApplication, _FakeDataSource]:
    container = Container()
    data_source = _FakeDataSource()
    container.register({"provide": _DATA_SOURCE_TOKEN, "useValue": data_source})
    scan_result = scan_module(_RootModule, container)
    fastapi_app = FastAPI(title="Austial (lifecycle test)")
    app = AustialApplication(container, fastapi_app, scan_result.controllers, [])
    app.use_global_interceptors(_AuditInterceptor)

    @app.get_http_adapter().on_event("startup")
    async def _init_data_source() -> None:
        await data_source.initialize()

    return app, data_source


async def _drive_lifespan(app: AustialApplication) -> None:
    """Manually drives the ASGI lifespan handshake exactly like uvicorn's
    ``Server.serve()`` does before accepting any connection: "lifespan.startup"
    first, "lifespan.shutdown" once the caller is done with the app."""
    events = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
    sent: list[dict] = []

    async def receive() -> dict:
        return next(events)

    async def send(message: dict) -> None:
        sent.append(message)

    await app({"type": "lifespan"}, receive, send)
    assert {"type": "lifespan.startup.complete"} in sent
    assert {"type": "lifespan.shutdown.complete"} in sent


@pytest.mark.asyncio
async def test_asgi_lifespan_startup_runs_before_route_building():
    """The actual bug scenario: ``uvicorn src.main:app`` / ``austial serve``
    route every scope -- including the lifespan one -- through ``__call__``.
    Route-building (and therefore ``_AuditInterceptor``'s DI resolution) must
    be deferred until after the lifespan handshake's ``"startup"`` handler has
    initialized the fake data source, not run eagerly on the lifespan scope
    itself."""
    app, data_source = _build_app()

    await _drive_lifespan(app)
    assert data_source.initialized is True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/ping")
        assert response.status_code == 200
        assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_eager_init_still_fails_before_startup_ran():
    """Sanity check that this is a real ordering bug, not a tautology:
    ``app.init()`` (the eager path ``austial.testing`` e2e tests rely on,
    where test authors control their own startup ordering) still builds
    routes immediately and still fails if called before the data source is
    initialized -- confirming the test above exercises the fix rather than
    something that always passed."""
    app, _data_source = _build_app()

    with pytest.raises(RuntimeError, match="DataSource.initialize"):
        await app.init()


async def test_objects_with_a_dynamic_getattr_are_not_treated_as_hook_owners() -> None:
    """A PyMongo database (or any proxy) answers every attribute name; only classes that define a hook get called."""
    from austial import AustialFactory, Module

    class Proxy:
        def __getattr__(self, name: str):
            return object()  # not callable: but a callable-returning proxy must not be called either

    class CallableProxy:
        def __getattr__(self, name: str):
            raise AssertionError(f"hook {name} must not be looked up on the instance")

    @Module(providers=[{"provide": "A", "useValue": Proxy()}, {"provide": "B", "useValue": CallableProxy()}])
    class Root:
        pass

    app = AustialFactory.create(Root)
    await app.init()
    await app.close()
