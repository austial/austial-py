"""APP_* global tokens, testing overrides/mocker, async providers, the complete ExecutionContext
and the logging system."""

from __future__ import annotations

import asyncio
import io
import json
from contextlib import redirect_stdout

import pytest
from httpx import ASGITransport, AsyncClient

from austial import (
    APP_FILTER,
    APP_GUARD,
    APP_INTERCEPTOR,
    APP_PIPE,
    AustialFactory,
    Body,
    CanActivate,
    Catch,
    ConsoleLogger,
    Controller,
    ExecutionContext,
    Get,
    Inject,
    Injectable,
    Logger,
    LoggerService,
    Module,
    NestInterceptor,
    NotFoundException,
    PipeTransform,
    Post,
    Query,
    UseGuards,
)
from austial.common.filters import ArgumentsHost, ExceptionFilter
from austial.core import AsyncProviderNotInitializedError, Container
from austial.core.module_scanner import scan_module
from austial.testing import Test

# ---------------------------------------------------------------------------------------------
# APP_GUARD / APP_PIPE / APP_INTERCEPTOR / APP_FILTER
# ---------------------------------------------------------------------------------------------

CALLS: list[str] = []


@Injectable()
class Settings:
    allowed_key = "secret"


class KeyGuard(CanActivate):
    def __init__(self, settings: Settings):  # constructor injection -- impossible with use_global_guards(Guard())
        self.settings = settings

    async def can_activate(self, context: ExecutionContext) -> bool:
        CALLS.append("guard")
        return context.get_request().headers.get("x-key") == self.settings.allowed_key


class UpperPipe(PipeTransform):
    def transform(self, value, metadata):
        CALLS.append("pipe")
        return value.upper() if isinstance(value, str) else value


class WrapInterceptor(NestInterceptor):
    def __init__(self, label: str = "wrapped"):
        self.label = label

    async def intercept(self, context, next):
        CALLS.append(f"interceptor:{self.label}")
        return {self.label: await next.handle()}


@Catch(NotFoundException)
class NotFoundToTeapot(ExceptionFilter):
    async def catch(self, exception, host: ArgumentsHost):
        from starlette.responses import JSONResponse

        return JSONResponse({"teapot": True}, status_code=418)


@Controller("g")
class GController:
    @Get("hello")
    async def hello(self, name: str = Query("name", default="bob")):
        return name

    @Get("missing")
    async def missing(self):
        raise NotFoundException()


@Module(
    controllers=[GController],
    providers=[
        Settings,
        {"provide": APP_GUARD, "useClass": KeyGuard},
        {"provide": APP_PIPE, "useClass": UpperPipe},
        {"provide": APP_INTERCEPTOR, "useClass": WrapInterceptor},
        {"provide": APP_INTERCEPTOR, "useFactory": lambda: WrapInterceptor("outer"), "inject": []},
        {"provide": APP_FILTER, "useClass": NotFoundToTeapot},
    ],
)
class GlobalsModule:
    pass


async def test_app_tokens_register_global_components_with_di() -> None:
    CALLS.clear()
    app = AustialFactory.create(GlobalsModule)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get("/g/hello")
        assert denied.status_code == 403  # KeyGuard got Settings injected and rejected the request

        ok = await client.get("/g/hello", headers={"x-key": "secret"})
        # Two APP_INTERCEPTORs, both applied (first registered is outermost); the pipe upper-cased the query value.
        assert ok.json() == {"wrapped": {"outer": "BOB"}}

        teapot = await client.get("/g/missing", headers={"x-key": "secret"})
        assert (teapot.status_code, teapot.json()) == (418, {"teapot": True})

    assert "guard" in CALLS and "pipe" in CALLS


async def test_app_guard_works_alongside_use_global_guards_and_registers_many() -> None:
    @Injectable()
    class First(CanActivate):
        async def can_activate(self, context) -> bool:
            CALLS.append("first")
            return True

    @Injectable()
    class Second(CanActivate):
        async def can_activate(self, context) -> bool:
            CALLS.append("second")
            return True

    @Controller("two")
    class TwoController:
        @Get()
        async def get(self):
            return "ok"

    CALLS.clear()
    module = await Test.create_testing_module(
        controllers=[TwoController],
        providers=[{"provide": APP_GUARD, "useClass": First}, {"provide": APP_GUARD, "useClass": Second}],
    ).compile()
    app = module.create_austial_application()

    class Manual(CanActivate):
        async def can_activate(self, context) -> bool:
            CALLS.append("manual")
            return True

    app.use_global_guards(Manual())
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/two")).json() == "ok"
    assert CALLS == ["manual", "first", "second"]  # use_global_* first, then DI registrations in order


async def test_app_filter_also_renders_errors_outside_route_handlers() -> None:
    @Controller("v")
    class VController:
        @Post()
        async def post(self, n: int = Body(embed=True)):
            return n

    @Catch()
    class AnyFilter(ExceptionFilter):
        async def catch(self, exception, host):
            from starlette.responses import JSONResponse

            return JSONResponse({"filtered": type(exception).__name__}, status_code=400)

    module = await Test.create_testing_module(
        controllers=[VController], providers=[{"provide": APP_FILTER, "useClass": AnyFilter}]
    ).compile()
    app = module.create_austial_application()
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v", json={"n": "not-an-int"})
    assert response.json() == {"filtered": "BadRequestException"}  # FastAPI's validation error -> APP_FILTER


# ---------------------------------------------------------------------------------------------
# testing overrides + use_mocker
# ---------------------------------------------------------------------------------------------


@Injectable()
class Repo:
    def find(self) -> str:
        return "real"


@Injectable()
class Service:
    def __init__(self, repo: Repo):
        self.repo = repo

    def get(self) -> str:
        return self.repo.find()


class RealGuard(CanActivate):
    async def can_activate(self, context) -> bool:
        return False


class AllowGuard(CanActivate):
    async def can_activate(self, context) -> bool:
        return True


@Controller("o")
class OController:
    def __init__(self, service: Service):
        self.service = service

    @Get()
    @UseGuards(RealGuard)
    async def get(self):
        return self.service.get()


class FakeRepo:
    def find(self) -> str:
        return "fake"


async def test_override_provider_value_class_and_factory() -> None:
    base = Test.create_testing_module(providers=[Repo, Service])
    assert (await base.compile()).get(Service).get() == "real"

    by_value = await (
        Test.create_testing_module(providers=[Repo, Service]).override_provider(Repo).use_value(FakeRepo()).compile()
    )
    assert by_value.get(Service).get() == "fake"

    by_class = await (
        Test.create_testing_module(providers=[Repo, Service]).override_provider(Repo).use_class(FakeRepo).compile()
    )
    assert by_class.get(Service).get() == "fake"

    by_factory = await (
        Test.create_testing_module(providers=[Repo, Service])
        .override_provider(Repo)
        .use_factory(lambda: FakeRepo())
        .compile()
    )
    assert by_factory.get(Service).get() == "fake"


async def test_override_guard_changes_the_route_outcome() -> None:
    plain = await Test.create_testing_module(controllers=[OController], providers=[Repo, Service]).compile()
    plain_app = plain.create_austial_application()
    await plain_app.init()
    async with AsyncClient(transport=ASGITransport(app=plain_app), base_url="http://test") as client:
        assert (await client.get("/o")).status_code == 403

    module = await (
        Test.create_testing_module(controllers=[OController], providers=[Repo, Service])
        .override_guard(RealGuard)
        .use_class(AllowGuard)
        .override_provider(Repo)
        .use_value(FakeRepo())
        .compile()
    )
    app = module.create_austial_application()
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/o")).json() == "fake"


async def test_override_pipe_interceptor_filter_aliases_exist() -> None:
    builder = Test.create_testing_module()
    for name in ("override_pipe", "override_interceptor", "override_filter", "override_guard"):
        assert getattr(builder, name)(object).use_value(1) is builder


async def test_use_mocker_supplies_unregistered_dependencies() -> None:
    mocked: list[object] = []

    def mocker(token):
        if token is Repo:
            mocked.append(token)
            return FakeRepo()
        return None

    module = await Test.create_testing_module(providers=[Service]).use_mocker(mocker).compile()
    assert module.get(Service).get() == "fake"
    assert mocked == [Repo]


async def test_testing_module_resolve_and_close_run_hooks() -> None:
    from austial import REQUEST, Scope

    events: list[str] = []

    @Injectable(scope=Scope.REQUEST)
    class PerRequest:
        pass

    @Injectable()
    class Closer:
        def on_module_destroy(self) -> None:
            events.append("destroyed")

        def on_module_init(self) -> None:
            events.append("init")

    module = await Test.create_testing_module(providers=[PerRequest, Closer]).compile()
    assert module.resolve(PerRequest) is not module.resolve(PerRequest)
    app = module.create_austial_application()
    await app.init()
    await module.close()
    assert events == ["init", "destroyed"]
    assert REQUEST == "REQUEST"


# ---------------------------------------------------------------------------------------------
# async providers
# ---------------------------------------------------------------------------------------------

BOOT: list[str] = []


async def connect(url: str) -> dict:
    await asyncio.sleep(0)
    BOOT.append(f"connect:{url}")
    return {"url": url}


async def make_client_for(conn: dict, settings: Settings) -> dict:
    BOOT.append("client")
    return {"conn": conn, "key": settings.allowed_key}


@Injectable()
class NeedsClient:
    def __init__(self, client=Inject("CLIENT")):
        self.client = client


@Controller("async")
class AsyncController:
    def __init__(self, needs: NeedsClient):
        self.needs = needs

    @Get()
    async def get(self):
        return self.needs.client


async def test_async_factory_providers_are_awaited_dependencies_first() -> None:
    BOOT.clear()
    providers = [
        Settings,
        {"provide": "CONN", "useFactory": connect, "inject": ["URL"]},
        {"provide": "URL", "useValue": "db://x"},
        {"provide": "CLIENT", "useFactory": make_client_for, "inject": ["CONN", Settings]},
        NeedsClient,
    ]
    module = await Test.create_testing_module(controllers=[AsyncController], providers=providers).compile()
    assert BOOT == ["connect:db://x", "client"]
    assert module.get(NeedsClient).client == {"conn": {"url": "db://x"}, "key": "secret"}


async def test_async_provider_resolves_through_a_real_app_and_errors_before_init() -> None:
    BOOT.clear()
    providers = [
        Settings,
        {"provide": "CONN", "useFactory": connect, "inject": ["URL"]},
        {"provide": "URL", "useValue": "db://y"},
        {"provide": "CLIENT", "useFactory": make_client_for, "inject": ["CONN", Settings]},
        NeedsClient,
    ]

    @Module(controllers=[AsyncController], providers=providers)
    class AsyncModule:
        pass

    app = AustialFactory.create(AsyncModule)
    with pytest.raises(AsyncProviderNotInitializedError, match="app.init"):
        app.get("CLIENT")
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/async")).json()["conn"] == {"url": "db://y"}
    assert BOOT.count("connect:db://y") == 1  # built once


async def test_async_provider_in_standalone_context_and_lifespan() -> None:
    BOOT.clear()

    @Module(
        providers=[{"provide": "CONN", "useFactory": connect, "inject": ["URL"]}, {"provide": "URL", "useValue": "u"}]
    )
    class CtxModule:
        pass

    ctx = await AustialFactory.create_application_context(CtxModule)
    assert ctx.get("CONN") == {"url": "u"}

    app = AustialFactory.create(CtxModule)
    async with app.get_http_adapter().router.lifespan_context(app.get_http_adapter()):
        assert app.get("CONN") == {"url": "u"}  # awaited by the ASGI lifespan startup


def test_async_factory_must_be_singleton() -> None:
    from austial import Scope

    with pytest.raises(ValueError, match="singleton"):
        Container().register({"provide": "X", "useFactory": connect, "scope": Scope.TRANSIENT})


@Injectable()
class PlainNeedsConn:
    def __init__(self, conn=Inject("CONN")):
        self.conn = conn


@Injectable()
class OuterOfPlain:
    def __init__(self, plain: PlainNeedsConn):
        self.plain = plain


async def test_async_provider_depended_on_by_a_plain_class_is_ready_first() -> None:
    BOOT.clear()
    container = Container()
    scan_module(
        Module(
            providers=[
                {"provide": "CONN", "useFactory": connect, "inject": ["URL"]},
                {"provide": "URL", "useValue": "z"},
                PlainNeedsConn,
                OuterOfPlain,
            ]
        )(type("R", (), {})),
        container,
    )
    await container.init_async_providers()
    assert container.resolve(OuterOfPlain).plain.conn == {"url": "z"}


# ---------------------------------------------------------------------------------------------
# ExecutionContext
# ---------------------------------------------------------------------------------------------


async def test_execution_context_is_complete() -> None:
    seen: dict = {}

    class Inspector(CanActivate):
        async def can_activate(self, context: ExecutionContext) -> bool:
            seen["type"] = context.get_type()
            seen["args"] = context.get_args()
            seen["response_is_arg1"] = context.get_response() is context.get_arg_by_index(1)
            seen["request_is_arg0"] = context.get_request() is context.get_arg_by_index(0)
            seen["http"] = context.switch_to_http() is context
            for method in (context.switch_to_ws, context.switch_to_rpc):
                with pytest.raises(NotImplementedError, match="no .* transport"):
                    method()
            response = context.get_response()
            assert response is not None
            response.headers["X-From-Guard"] = "yes"
            return True

    @Controller("ctx")
    class CtxController:
        @Get()
        @UseGuards(Inspector)
        async def get(self):
            return "ok"

    module = await Test.create_testing_module(controllers=[CtxController], providers=[Inspector]).compile()
    app = module.create_austial_application()
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ctx")
    assert seen["type"] == "http" and len(seen["args"]) == 2
    assert seen["response_is_arg1"] and seen["request_is_arg0"] and seen["http"]
    assert response.headers["x-from-guard"] == "yes"  # headers set on the context's response are sent


# ---------------------------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------------------------


class Recording(LoggerService):
    def __init__(self) -> None:
        self.records: list[tuple[str, str, str | None]] = []

    def log(self, message, context=None):
        self.records.append(("log", message, context))

    def error(self, message, context=None):
        self.records.append(("error", message, context))

    def warn(self, message, context=None):
        self.records.append(("warn", message, context))


@pytest.fixture(autouse=True)
def _restore_logger():
    yield
    Logger.override_logger(True)
    Logger.flush()


def test_custom_logger_service_receives_records_and_optional_levels_fall_back() -> None:
    recording = Recording()
    Logger.override_logger(recording)
    log = Logger("Cats")
    log.log("a")
    log.warn("b")
    log.error("c", "Override")
    log.debug("d")  # not implemented by Recording -> falls back to log()
    log.verbose("e")
    log.fatal("f")  # -> error()
    assert recording.records == [
        ("log", "a", "Cats"),
        ("warn", "b", "Cats"),
        ("error", "c", "Override"),
        ("log", "d", "Cats"),
        ("log", "e", "Cats"),
        ("error", "f", "Cats"),
    ]


def test_log_levels_filter_the_console_logger() -> None:
    Logger.override_logger(["error"])
    out = io.StringIO()
    with redirect_stdout(out):
        from austial.common import logger as logger_module

        logger_module._console.file = out  # noqa: SLF001 - capture rich output
        Logger("X").log("hidden")
        Logger("X").error("shown")
    text = out.getvalue()
    assert "shown" in text and "hidden" not in text


def test_false_silences_everything_and_true_restores() -> None:
    recording = Recording()
    Logger.override_logger(recording)
    Logger.override_logger(False)
    Logger("X").error("nobody hears this")
    assert recording.records == []
    Logger.override_logger(True)
    assert isinstance(Logger.active_logger(), ConsoleLogger)


def test_json_output(capsys) -> None:
    Logger.override_logger(ConsoleLogger(json_output=True))
    Logger("Json").log("hello")
    Logger("Json").error("bad")
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert (record["level"], record["context"], record["message"]) == ("log", "Json", "hello")
    assert json.loads(captured.err)["level"] == "error"


def test_buffering_holds_records_until_a_logger_is_attached() -> None:
    Logger.attach_buffer()
    Logger("Boot").log("early")
    Logger("Boot").warn("also early")
    recording = Recording()
    Logger.override_logger(recording)
    assert recording.records == []  # still buffered
    Logger.flush()
    assert recording.records == [("log", "early", "Boot"), ("warn", "also early", "Boot")]
    Logger("Boot").log("live")  # buffering stopped
    assert recording.records[-1] == ("log", "live", "Boot")


async def test_factory_logger_option_and_use_logger() -> None:
    recording = Recording()

    @Module()
    class Empty:
        pass

    AustialFactory.create(Empty, logger=recording)
    Logger("T").log("through the factory option")
    assert ("log", "through the factory option", "T") in recording.records

    late = Recording()
    app = AustialFactory.create(Empty, buffer_logs=True)
    Logger("T").log("held")
    assert late.records == []
    app.use_logger(late)
    assert ("log", "held", "T") in late.records

    silent = AustialFactory.create(Empty, logger=False)
    assert silent is not None
    ctx = await AustialFactory.create_application_context(Empty, logger=["error"])
    await ctx.close()
