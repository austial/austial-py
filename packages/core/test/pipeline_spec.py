"""The request pipeline as a whole -- global guards/pipes/interceptors/filters and their order,
exception rendering, module middleware, CORS -- plus a real-socket end-to-end test that boots
uvicorn so the ASGI lifespan (and therefore the lifecycle hooks) runs for real."""

from __future__ import annotations

import asyncio
import socket

import httpx
import pytest
import uvicorn
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from austial import (
    ArgumentsHost,
    AustialFactory,
    BadRequestException,
    Body,
    CanActivate,
    Catch,
    Controller,
    ExceptionFilter,
    ExecutionContext,
    ForbiddenException,
    Get,
    Global,
    Injectable,
    MiddlewareConsumer,
    Module,
    NestInterceptor,
    NestMiddleware,
    NotFoundException,
    PipeTransform,
    Post,
    Query,
    Reflector,
    TransformInterceptor,
    UseFilters,
    UseGuards,
    ValidationPipe,
)
from austial.common.lifecycle import OnApplicationBootstrap, OnApplicationShutdown
from austial.core.metadata import set_metadata
from austial.testing import Test

TRACE: list[str] = []


@pytest.fixture(autouse=True)
def _clear_trace() -> None:
    TRACE.clear()


class TraceGuard(CanActivate):
    def __init__(self, name: str, allow: bool = True):
        self.name, self.allow = name, allow

    async def can_activate(self, context: ExecutionContext) -> bool:
        TRACE.append(f"guard:{self.name}")
        return self.allow


class TracePipe(PipeTransform):
    def __init__(self, name: str):
        self.name = name

    def transform(self, value, metadata):
        TRACE.append(f"pipe:{self.name}")
        return value


class TraceInterceptor(NestInterceptor):
    def __init__(self, name: str):
        self.name = name

    async def intercept(self, context, next):
        TRACE.append(f"in:{self.name}")
        result = await next.handle()
        TRACE.append(f"out:{self.name}")
        return result


class CreateDto(BaseModel):
    name: str


@Controller("things")
@UseGuards(TraceGuard("controller"))
class ThingsController:
    @Get("ok")
    @UseGuards(TraceGuard("route"))
    async def ok(self, q: str = Query("q", default="x")):
        TRACE.append("handler")
        return {"q": q}

    @Get("denied")
    @UseGuards(TraceGuard("deny", allow=False))
    async def denied(self):
        TRACE.append("handler")  # must never run

    @Get("missing")
    async def missing(self):
        raise NotFoundException("no such thing")

    @Get("boom")
    async def boom(self):
        raise RuntimeError("kaboom")

    @Post()
    async def create(self, dto: CreateDto = Body()):
        return dto


async def _client(controllers, *, configure=None, providers=()) -> AsyncClient:
    module = await Test.create_testing_module(controllers=list(controllers), providers=list(providers)).compile()
    app = module.create_austial_application()
    if configure:
        configure(app)
    await app.init()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_pipeline_order_is_guards_pipes_interceptors_handler() -> None:
    def configure(app):
        app.use_global_guards(TraceGuard("global"))
        app.use_global_pipes(TracePipe("global"))
        app.use_global_interceptors(TraceInterceptor("global"), TraceInterceptor("second"))

    async with await _client([ThingsController], configure=configure) as client:
        response = await client.get("/things/ok?q=1")
    assert response.json() == {"q": "1"}
    # Guards: global -> controller -> route. Interceptors nest: first declared is outermost.
    assert TRACE == [
        "guard:global",
        "guard:controller",
        "guard:route",
        "pipe:global",
        "in:global",
        "in:second",
        "handler",
        "out:second",
        "out:global",
    ]


async def test_denied_guard_short_circuits_with_403_and_nest_shaped_body() -> None:
    async with await _client([ThingsController]) as client:
        response = await client.get("/things/denied")
    body = response.json()
    assert response.status_code == 403
    assert (body["statusCode"], body["message"], body["error"]) == (403, "Forbidden resource", "Forbidden")
    assert body["path"] == "/things/denied" and "timestamp" in body
    assert "handler" not in TRACE


async def test_default_filter_renders_http_and_unhandled_exceptions() -> None:
    async with await _client([ThingsController]) as client:
        missing = await client.get("/things/missing")
        assert missing.status_code == 404 and missing.json()["message"] == "no such thing"

        boom = await client.get("/things/boom")
        assert boom.status_code == 500
        assert boom.json()["message"] == "Internal Server Error"  # internals are never leaked


async def test_request_validation_errors_use_the_nest_shape() -> None:
    async with await _client([ThingsController]) as client:
        response = await client.post("/things", json={"wrong": 1})
    body = response.json()
    assert response.status_code == 400
    assert body["error"] == "Bad Request"
    assert body["message"][0]["loc"] == ["body", "name"]


@Catch(NotFoundException)
class NotFoundOnlyFilter(ExceptionFilter):
    async def catch(self, exception, host: ArgumentsHost):
        from starlette.responses import JSONResponse

        return JSONResponse({"custom": "not-found", "path": host.get_request().url.path}, status_code=404)


@Catch()  # no types: catches everything
class TeapotFilter(ExceptionFilter):
    async def catch(self, exception, host):
        from starlette.responses import JSONResponse

        return JSONResponse({"caught": type(exception).__name__}, status_code=418)


async def test_use_filters_scopes_and_catch_selects_exception_types() -> None:
    @Controller("filtered")
    @UseFilters(NotFoundOnlyFilter)
    class FilteredController:
        @Get("nf")
        async def nf(self):
            raise NotFoundException()

        @Get("bad")
        async def bad(self):
            raise BadRequestException("nope")  # not matched by the filter -> re-raised -> default handler

        @Get("all")
        @UseFilters(TeapotFilter)
        async def all(self):
            raise ForbiddenException("x")

    async with await _client([FilteredController]) as client:
        nf = await client.get("/filtered/nf")
        assert (nf.status_code, nf.json()) == (404, {"custom": "not-found", "path": "/filtered/nf"})
        assert (await client.get("/filtered/all")).json() == {"caught": "ForbiddenException"}
        # The class-level filter doesn't match BadRequest, so the default filter renders it.
        bad = await client.get("/filtered/bad")
        assert (bad.status_code, bad.json()["message"]) == (400, "nope")


async def test_global_filter_replaces_the_default() -> None:
    def configure(app):
        app.use_global_filters(TeapotFilter())

    async with await _client([ThingsController], configure=configure) as client:
        response = await client.get("/things/missing")
    assert (response.status_code, response.json()) == (418, {"caught": "NotFoundException"})


async def test_validation_pipe_and_transform_interceptor_globally() -> None:
    def configure(app):
        app.use_global_pipes(ValidationPipe())
        app.use_global_interceptors(TransformInterceptor())

    async with await _client([ThingsController], configure=configure) as client:
        response = await client.post("/things", json={"name": "n"})
    body = response.json()
    assert body["data"] == {"name": "n"} and "timestamp" in body


# ---------------------------------------------------------------------------------------------
# middleware through a module's configure()
# ---------------------------------------------------------------------------------------------


class Stamp(NestMiddleware):
    def __init__(self, label: str = "stamp"):
        self.label = label

    async def use(self, request, call_next):
        TRACE.append(f"mw:{self.label}")
        response = await call_next()
        response.headers[f"x-{self.label}"] = "1"
        return response


@Controller("mw")
class MwController:
    @Get("a")
    async def a(self):
        return {"ok": True}

    @Get("b")
    async def b(self):
        return {"ok": True}


@Module(controllers=[MwController])
class MwModule:
    def configure(self, consumer: MiddlewareConsumer) -> None:
        consumer.apply(Stamp("everywhere")).for_routes("*")
        consumer.apply(Stamp("only-a")).for_routes("/mw/a")


async def test_module_middleware_applies_to_matching_routes_only() -> None:
    app = AustialFactory.create(MwModule)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        a = await client.get("/mw/a")
        b = await client.get("/mw/b")
    assert "x-everywhere" in a.headers and "x-only-a" in a.headers
    assert "x-everywhere" in b.headers and "x-only-a" not in b.headers
    assert TRACE[:2] == ["mw:everywhere", "mw:only-a"]  # declaration order = outermost first


async def test_enable_cors() -> None:
    def configure(app):
        app.enable_cors(allow_origins=["https://app.example.com"])

    async with await _client([ThingsController], configure=configure) as client:
        response = await client.get("/things/ok", headers={"Origin": "https://app.example.com"})
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"


# ---------------------------------------------------------------------------------------------
# Global modules, Reflector
# ---------------------------------------------------------------------------------------------


def test_global_decorator_marks_module_metadata() -> None:
    from austial.core.metadata import MODULE_METADATA, get_metadata

    @Global
    @Module()
    class SharedModule:
        pass

    assert get_metadata(MODULE_METADATA, SharedModule).is_global is True


def test_reflector_get_merge_and_override() -> None:
    KEY = "test:roles"

    @set_metadata(KEY, ["admin"])
    class Cls:
        @set_metadata(KEY, ["editor"])
        def handler(self): ...

        def bare(self): ...

    reflector = Reflector()
    assert reflector.get(KEY, Cls.handler) == ["editor"]
    assert reflector.get("missing", Cls, "fallback") == "fallback"
    assert reflector.get_all_and_merge(KEY, [Cls.handler, Cls]) == ["editor", "admin"]
    assert reflector.get_all_and_override(KEY, [Cls.bare, Cls]) == ["admin"]
    assert reflector.get_all_and_override("missing", [Cls]) is None


# ---------------------------------------------------------------------------------------------
# a real server: uvicorn drives the ASGI lifespan, so hooks fire exactly as in production
# ---------------------------------------------------------------------------------------------

LIVE: list[str] = []


@Injectable()
class LiveProbe(OnApplicationBootstrap, OnApplicationShutdown):
    def on_application_bootstrap(self) -> None:
        LIVE.append("bootstrap")

    def on_application_shutdown(self, signal: str | None = None) -> None:
        LIVE.append("shutdown")


@Controller("live")
class LiveController:
    def __init__(self, probe: LiveProbe):
        self.probe = probe

    @Get()
    async def live(self):
        return {"events": list(LIVE)}


@Module(controllers=[LiveController], providers=[LiveProbe])
class LiveModule:
    pass


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def test_hooks_run_under_a_real_uvicorn_lifespan() -> None:
    LIVE.clear()
    app = AustialFactory.create(LiveModule)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    task = asyncio.create_task(server.serve())
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            for _ in range(100):
                if server.started:
                    break
                await asyncio.sleep(0.05)
            assert server.started, "uvicorn did not start"
            response = await client.get("/live")
        assert response.json() == {"events": ["bootstrap"]}  # bootstrap ran before the first request
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, timeout=10)
    assert LIVE == ["bootstrap", "shutdown"]
