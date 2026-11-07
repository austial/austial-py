"""Core/DI features: lifecycle hooks, ``useExisting``, ``ModuleRef``, ``forward_ref``,
request-scoped providers + the ``REQUEST`` token, ``DiscoveryService``, ``LazyModuleLoader``,
``ConfigurableModuleBuilder`` and standalone application contexts."""

from __future__ import annotations

import asyncio
import signal

import pytest
from httpx import ASGITransport, AsyncClient

from austial import (
    REQUEST,
    AustialFactory,
    ConfigurableModuleBuilder,
    ContextIdFactory,
    Controller,
    DiscoveryService,
    Get,
    Inject,
    Injectable,
    LazyModuleLoader,
    Module,
    ModuleRef,
    OnApplicationBootstrap,
    OnModuleDestroy,
    OnModuleInit,
    Req,
    Scope,
    forward_ref,
)
from austial.core import RequestScopeError
from austial.core.container import CircularDependencyError, Container
from austial.core.metadata import set_metadata
from austial.core.module_scanner import scan_module
from austial.testing import Test

# ---------------------------------------------------------------------------------------------
# lifecycle hooks
# ---------------------------------------------------------------------------------------------


def _recorder() -> list[str]:
    return []


EVENTS: list[str] = []


@Injectable()
class Database(OnModuleInit, OnModuleDestroy):
    async def on_module_init(self) -> None:
        EVENTS.append("db:init")

    async def on_module_destroy(self) -> None:
        EVENTS.append("db:destroy")


@Injectable()
class Cache:
    """Defines hooks by name only -- no interface subclassing needed."""

    def __init__(self, db: Database):
        self.db = db

    def on_module_init(self) -> None:  # sync hooks work too
        EVENTS.append("cache:init")

    def on_application_bootstrap(self) -> None:
        EVENTS.append("cache:bootstrap")

    def before_application_shutdown(self, signal: str | None = None) -> None:
        EVENTS.append(f"cache:before-shutdown:{signal}")

    def on_application_shutdown(self) -> None:  # signal parameter is optional
        EVENTS.append("cache:shutdown")


@Injectable()
class Untouched:
    constructed = False

    def __init__(self) -> None:
        Untouched.constructed = True


@Module(providers=[Database])
class DbModule:
    pass


@Module(imports=[DbModule], providers=[Cache, Untouched])
class AppModule(OnApplicationBootstrap):
    def on_application_bootstrap(self) -> None:
        EVENTS.append("module:bootstrap")


@pytest.fixture(autouse=True)
def _reset_events() -> None:
    EVENTS.clear()
    Untouched.constructed = False


async def test_init_runs_hooks_dependencies_first_and_close_runs_them_in_reverse() -> None:
    app = AustialFactory.create(AppModule)
    await app.init()
    assert EVENTS == ["db:init", "cache:init", "cache:bootstrap", "module:bootstrap"]

    EVENTS.clear()
    await app.close(signal="SIGTERM")
    assert EVENTS == ["db:destroy", "cache:before-shutdown:SIGTERM", "cache:shutdown"]


async def test_providers_without_hooks_stay_lazy() -> None:
    app = AustialFactory.create(AppModule)
    await app.init()
    assert Untouched.constructed is False


async def test_init_is_idempotent_and_close_without_init_is_a_noop() -> None:
    app = AustialFactory.create(AppModule)
    await app.close()
    assert EVENTS == []
    await app.init()
    await app.init()
    assert EVENTS.count("db:init") == 1


async def test_asgi_lifespan_runs_hooks_after_startup_handlers() -> None:
    app = AustialFactory.create(AppModule)
    app.get_http_adapter().router.on_startup.append(lambda: EVENTS.append("on_event:startup"))
    app.get_http_adapter().router.on_shutdown.append(lambda: EVENTS.append("on_event:shutdown"))

    async with app.get_http_adapter().router.lifespan_context(app.get_http_adapter()):
        assert EVENTS == ["on_event:startup", "db:init", "cache:init", "cache:bootstrap", "module:bootstrap"]
        EVENTS.clear()
    assert EVENTS == ["db:destroy", "cache:before-shutdown:None", "cache:shutdown", "on_event:shutdown"]


async def test_hooks_run_once_when_init_precedes_lifespan() -> None:
    app = AustialFactory.create(AppModule)
    await app.init()
    async with app.get_http_adapter().router.lifespan_context(app.get_http_adapter()):
        pass
    assert EVENTS.count("db:init") == 1
    assert EVENTS.count("db:destroy") == 1


async def test_standalone_application_context_runs_hooks_and_resolves_providers() -> None:
    ctx = await AustialFactory.create_application_context(AppModule)
    assert EVENTS[:2] == ["db:init", "cache:init"]
    assert isinstance(ctx.get(Cache).db, Database)
    await ctx.close()
    assert "db:destroy" in EVENTS


async def test_enable_shutdown_hooks_closes_on_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import types

    reraised: list[int] = []
    # Only the module under test sees the fake `os`, so the test can still deliver a real signal.
    fake_os = types.SimpleNamespace(getpid=os.getpid, kill=lambda pid, sig: reraised.append(sig))
    monkeypatch.setattr("austial.core.application_context.os", fake_os)

    ctx = await AustialFactory.create_application_context(AppModule)
    ctx.enable_shutdown_hooks("SIGUSR1")  # already initialised, so the handler is installed now

    os.kill(os.getpid(), signal.SIGUSR1)
    for _ in range(100):
        if reraised:
            break
        await asyncio.sleep(0.01)

    assert reraised == [signal.SIGUSR1]  # the signal is handed back once shutdown has finished
    assert "cache:before-shutdown:SIGUSR1" in EVENTS


# ---------------------------------------------------------------------------------------------
# useExisting, ModuleRef
# ---------------------------------------------------------------------------------------------


@Injectable()
class RealLogger:
    pass


async def test_use_existing_aliases_the_same_instance() -> None:
    module = await Test.create_testing_module(
        providers=[RealLogger, {"provide": "LOGGER", "useExisting": RealLogger}]
    ).compile()
    assert module.get("LOGGER") is module.get(RealLogger)


@Injectable()
class Dispatcher:
    def __init__(self, module_ref: ModuleRef):
        self.module_ref = module_ref


async def test_module_ref_is_injectable_and_resolves_get_has_create() -> None:
    module = await Test.create_testing_module(providers=[Dispatcher, RealLogger]).compile()
    ref = module.get(Dispatcher).module_ref
    assert ref.get(RealLogger) is module.get(RealLogger)
    assert ref.has(RealLogger)
    assert not ref.has("NOPE")
    created = ref.create(Dispatcher)
    assert created is not module.get(Dispatcher)
    assert created.module_ref is ref


# ---------------------------------------------------------------------------------------------
# forward_ref
# ---------------------------------------------------------------------------------------------


@Injectable()
class Chicken:
    def __init__(self, egg=Inject(forward_ref(lambda: Egg))):
        self.egg = egg

    def name(self) -> str:
        return "chicken"


@Injectable()
class Egg:
    def __init__(self, chicken: Chicken):
        self.chicken = chicken

    def name(self) -> str:
        return "egg"


async def test_forward_ref_breaks_a_provider_cycle() -> None:
    module = await Test.create_testing_module(providers=[Chicken, Egg]).compile()
    chicken = module.get(Chicken)
    assert chicken.egg.name() == "egg"  # lazy proxy resolves on first use
    assert chicken.egg.chicken is chicken
    assert module.get(Egg).chicken is chicken


@Injectable()
class Left:
    def __init__(self, right: "Right"):  # noqa: UP037
        self.right = right


@Injectable()
class Right:
    def __init__(self, left: Left):
        self.left = left


async def test_plain_cycle_still_reports_a_helpful_error() -> None:
    module = await Test.create_testing_module(providers=[Left, Right]).compile()
    with pytest.raises(CircularDependencyError, match="forward_ref"):
        module.get(Left)


async def test_forward_ref_in_module_imports() -> None:
    @Module(providers=[RealLogger], exports=[RealLogger])
    class LaterModule:
        pass

    @Module(imports=[forward_ref(lambda: LaterModule)])
    class EarlierModule:
        pass

    container = Container()
    scan_module(EarlierModule, container)
    assert container.resolve(RealLogger) is container.resolve(RealLogger)


# ---------------------------------------------------------------------------------------------
# request scope
# ---------------------------------------------------------------------------------------------


@Injectable(scope=Scope.REQUEST)
class RequestId:
    counter = 0

    def __init__(self) -> None:
        RequestId.counter += 1
        self.value = RequestId.counter


@Injectable()
class UsesRequestId:  # DEFAULT scope, but scope bubbles up from RequestId
    def __init__(self, request_id: RequestId):
        self.request_id = request_id


@Injectable()
class PathReader:  # depends on the REQUEST token -> implicitly request-scoped
    def __init__(self, request=Inject(REQUEST)):
        self.request = request


@Controller("scoped")
class ScopedController:
    def __init__(self, uses: UsesRequestId, reader: PathReader, request_id: RequestId):
        self.uses = uses
        self.reader = reader
        self.request_id = request_id

    @Get()
    async def show(self, req: Req):
        return {
            "bubbled_same": self.uses.request_id is self.request_id,
            "id": self.request_id.value,
            "path": self.reader.request.url.path,
            "request_is_current": self.reader.request is req,
        }


async def _scoped_client():
    module = await Test.create_testing_module(
        controllers=[ScopedController], providers=[RequestId, UsesRequestId, PathReader]
    ).compile()
    app = module.create_austial_application()
    await app.init()
    return module, AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_request_scoped_providers_are_built_per_request_and_shared_within_one() -> None:
    RequestId.counter = 0
    _, client = await _scoped_client()
    async with client:
        first = (await client.get("/scoped")).json()
        second = (await client.get("/scoped")).json()
    assert first == {"bubbled_same": True, "id": 1, "path": "/scoped", "request_is_current": True}
    assert second["id"] == 2 and second["bubbled_same"] is True


async def test_request_scoped_controller_is_not_built_at_startup() -> None:
    RequestId.counter = 0
    await _scoped_client()
    assert RequestId.counter == 0


async def test_resolving_request_scoped_provider_outside_a_request_explains_how() -> None:
    module = await Test.create_testing_module(providers=[RequestId]).compile()
    with pytest.raises(RequestScopeError, match="ModuleRef.resolve"):
        module.get(RequestId)


async def test_module_ref_resolve_with_context_id() -> None:
    RequestId.counter = 0
    module = await Test.create_testing_module(providers=[RequestId, ModuleRef]).compile()
    ref = module.get(ModuleRef)
    ctx = ContextIdFactory.create()
    assert ref.resolve(RequestId, ctx) is ref.resolve(RequestId, ctx)
    assert ref.resolve(RequestId, ContextIdFactory.create()) is not ref.resolve(RequestId, ctx)


@Injectable()
class RequestScopedGuard:
    def __init__(self, request_id: RequestId):
        self.request_id = request_id

    async def can_activate(self, context) -> bool:
        context.get_request().state.guard_saw = self.request_id.value
        return True


async def test_request_scoped_guard_shares_the_handlers_request_scope() -> None:
    from austial import UseGuards

    @Controller("g")
    class GuardedController:
        def __init__(self, request_id: RequestId):
            self.request_id = request_id

        @Get()
        @UseGuards(RequestScopedGuard)
        async def show(self, req: Req):
            return {"same": req.state.guard_saw == self.request_id.value}

    module = await Test.create_testing_module(controllers=[GuardedController], providers=[RequestId]).compile()
    app = module.create_austial_application()
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/g")).json() == {"same": True}


async def test_app_resolve_builds_request_scoped_provider() -> None:
    RequestId.counter = 0
    app = AustialFactory.create(Module(providers=[RequestId])(type("M", (), {})))
    assert app.resolve(RequestId).value == 1
    assert app.resolve(RequestId).value == 2


# ---------------------------------------------------------------------------------------------
# DiscoveryService
# ---------------------------------------------------------------------------------------------

TOPIC = "test:topic"


def Topic(name: str):
    return set_metadata(TOPIC, name)


@Injectable()
class Handlers:
    @Topic("created")
    def on_created(self) -> str:
        return "created!"

    def helper(self) -> str:
        return "ignored"


@Controller("disc")
class DiscController:
    pass


async def test_discovery_lists_providers_controllers_and_decorated_methods() -> None:
    module = await Test.create_testing_module(controllers=[DiscController], providers=[Handlers]).compile()
    discovery = module.get(DiscoveryService)

    provider_tokens = [w.token for w in discovery.get_providers()]
    assert Handlers in provider_tokens
    assert ModuleRef not in provider_tokens and DiscoveryService not in provider_tokens
    assert [w.token for w in discovery.get_controllers()] == [DiscController]

    methods = discovery.get_methods_with_metadata(TOPIC)
    assert len(methods) == 1
    wrapper, method_name, topic = methods[0]
    assert (wrapper.token, method_name, topic) == (Handlers, "on_created", "created")
    assert getattr(wrapper.instance, method_name)() == "created!"


# ---------------------------------------------------------------------------------------------
# LazyModuleLoader
# ---------------------------------------------------------------------------------------------


async def test_lazy_module_loader_registers_module_on_demand_and_runs_its_hooks() -> None:
    @Injectable()
    class ReportsService(OnModuleInit):
        def on_module_init(self) -> None:
            EVENTS.append("reports:init")

        def build(self) -> str:
            return "report"

    @Module(providers=[ReportsService])
    class ReportsModule:
        pass

    app = AustialFactory.create(AppModule)
    await app.init()
    assert not app.get(ModuleRef).has(ReportsService)

    loader = app.get(LazyModuleLoader)
    ref = await loader.load(lambda: ReportsModule)
    assert ref.get(ReportsService).build() == "report"
    assert EVENTS[-1] == "reports:init"

    await loader.load(ReportsModule)  # loading twice doesn't re-run hooks
    assert EVENTS.count("reports:init") == 1


# ---------------------------------------------------------------------------------------------
# ConfigurableModuleBuilder
# ---------------------------------------------------------------------------------------------

mail = ConfigurableModuleBuilder().set_class_method_name("for_root").build()


@Injectable()
class MailService:
    def __init__(self, options=Inject(mail.options_token)):
        self.options = options


@Module(providers=[MailService], exports=[MailService])
class MailModule(mail.module_class):  # type: ignore[name-defined]
    pass


@Injectable()
class MailOptionsFactory:
    def create(self) -> dict:
        return {"host": "from-factory-class"}


@Injectable()
class SmtpSettings:
    host = "from-injected-settings"


@Module(providers=[SmtpSettings], exports=[SmtpSettings])
class SettingsModule:
    pass


async def _mail_service(dynamic) -> MailService:
    module = await Test.create_testing_module(imports=[dynamic]).compile()
    return module.get(MailService)


async def test_configurable_module_for_root() -> None:
    service = await _mail_service(MailModule.for_root({"host": "smtp.example.com"}))
    assert service.options == {"host": "smtp.example.com"}


async def test_configurable_module_async_use_factory_with_inject() -> None:
    dynamic = MailModule.for_root_async(
        use_factory=lambda settings: {"host": settings.host}, inject=[SmtpSettings], imports=[SettingsModule]
    )
    assert (await _mail_service(dynamic)).options == {"host": "from-injected-settings"}


async def test_configurable_module_async_use_class_and_use_existing() -> None:
    assert (await _mail_service(MailModule.for_root_async(use_class=MailOptionsFactory))).options == {
        "host": "from-factory-class"
    }

    @Module(providers=[MailOptionsFactory], exports=[MailOptionsFactory])
    class FactoryModule:
        pass

    dynamic = MailModule.for_root_async(use_existing=MailOptionsFactory, imports=[FactoryModule])
    assert (await _mail_service(dynamic)).options == {"host": "from-factory-class"}


def test_configurable_module_async_requires_exactly_one_source() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        MailModule.for_root_async()


def test_configurable_module_extras_shape_the_dynamic_module() -> None:
    from dataclasses import replace  # noqa: F401

    built = (
        ConfigurableModuleBuilder()
        .set_class_method_name("register")
        .set_extras({"tag": "default"}, lambda module, extras: _tag(module, extras["tag"]))
        .build()
    )

    class M(built.module_class):  # type: ignore[name-defined]
        pass

    assert M.register({}).exports[-1] == "tag:default"
    assert M.register({}, tag="custom").exports[-1] == "tag:custom"


def _tag(module, tag):
    module.exports.append(f"tag:{tag}")
    return module


@Injectable()
class AsyncMailOptionsFactory:
    async def create(self) -> dict:
        await asyncio.sleep(0)
        return {"host": "from-async-create"}


async def test_configurable_module_supports_async_create_and_async_use_factory() -> None:
    # `async def create()` on a use_class source: the options are an async provider, awaited by compile()/init()
    assert (await _mail_service(MailModule.for_root_async(use_class=AsyncMailOptionsFactory))).options == {
        "host": "from-async-create"
    }

    @Module(providers=[AsyncMailOptionsFactory], exports=[AsyncMailOptionsFactory])
    class AsyncFactoryModule:
        pass

    existing = MailModule.for_root_async(use_existing=AsyncMailOptionsFactory, imports=[AsyncFactoryModule])
    assert (await _mail_service(existing)).options == {"host": "from-async-create"}

    async def fetch_options(settings) -> dict:
        await asyncio.sleep(0)
        return {"host": settings.host}

    via_factory = MailModule.for_root_async(use_factory=fetch_options, inject=[SmtpSettings], imports=[SettingsModule])
    assert (await _mail_service(via_factory)).options == {"host": "from-injected-settings"}
