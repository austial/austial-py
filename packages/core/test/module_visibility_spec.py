"""Strict module visibility, app.select(), and the module graph."""

from __future__ import annotations

import json

import pytest

from austial import (
    AustialFactory,
    Controller,
    Get,
    Global,
    Injectable,
    Module,
    ModuleRef,
    ModuleVisibilityError,
)
from austial.core.container import Container
from austial.core.module_graph import ModuleGraph
from austial.core.module_scanner import scan_module

# module-level classes: DI hints must resolve, so nothing here is defined inside a function


@Injectable()
class Mailer:
    pass


@Injectable()
class Secrets:
    pass


@Injectable()
class SharedClock:
    pass


@Injectable()
class Audit:
    pass


@Module(providers=[Mailer, Secrets], exports=[Mailer])  # Secrets is private
class MailModule:
    pass


@Global
@Module(providers=[SharedClock], exports=[SharedClock])
class ClockModule:
    pass


@Module(imports=[MailModule], exports=[MailModule])  # re-exports MailModule's exports
class NotificationsModule:
    pass


@Injectable()
class OrdersService:
    def __init__(self, mailer: Mailer, clock: SharedClock):  # Mailer via import, SharedClock via @Global
        self.mailer, self.clock = mailer, clock


@Injectable()
class SneakyService:
    def __init__(self, secrets: Secrets):  # MailModule never exports Secrets
        self.secrets = secrets


@Injectable()
class StrangerService:
    def __init__(self, mailer: Mailer):  # OtherModule doesn't import MailModule
        self.mailer = mailer


@Injectable()
class ViaReexport:
    def __init__(self, mailer: Mailer):  # imports NotificationsModule, which re-exports MailModule
        self.mailer = mailer


@Controller("orders")
class OrdersController:
    def __init__(self, orders: OrdersService):
        self.orders = orders

    @Get()
    async def get(self):
        return "ok"


@Module(
    imports=[MailModule, ClockModule],
    providers=[OrdersService],
    controllers=[OrdersController],
    exports=[OrdersService],
)
class OrdersModule:
    pass


@Module(imports=[MailModule], providers=[SneakyService])
class SneakyModule:
    pass


@Module(providers=[StrangerService])
class OtherModule:
    pass


@Module(imports=[NotificationsModule, ClockModule], providers=[ViaReexport])
class ReexportConsumerModule:
    pass


@Module(imports=[OrdersModule, SneakyModule, OtherModule, ReexportConsumerModule])
class AppModule:
    pass


def strict_app():
    return AustialFactory.create(AppModule, strict_modules=True)


def test_allowed_injection_paths_resolve() -> None:
    app = strict_app()
    assert isinstance(app.get(OrdersService).mailer, Mailer)  # imported module's export
    assert isinstance(app.get(OrdersService).clock, SharedClock)  # global module's export
    assert isinstance(app.get(ViaReexport).mailer, Mailer)  # re-exported through NotificationsModule
    assert isinstance(app.get(OrdersController).orders, OrdersService)  # same module


def test_private_provider_is_not_injectable_from_an_importing_module() -> None:
    with pytest.raises(ModuleVisibilityError) as caught:
        strict_app().get(SneakyService)
    message = str(caught.value)
    assert "SneakyService" in message and "Secrets" in message and "SneakyModule" in message
    assert "exports" in message


def test_provider_from_an_unimported_module_is_rejected() -> None:
    with pytest.raises(ModuleVisibilityError, match="StrangerService"):
        strict_app().get(StrangerService)


def test_default_mode_stays_permissive() -> None:
    app = AustialFactory.create(AppModule)  # strict_modules is opt-in
    assert isinstance(app.get(SneakyService).secrets, Secrets)
    assert isinstance(app.get(StrangerService).mailer, Mailer)


@Injectable()
class UsesModuleRef:
    def __init__(self, ref: ModuleRef):
        self.ref = ref


@Module(providers=[UsesModuleRef])
class AloneModule:
    pass


def test_framework_tokens_are_always_visible() -> None:
    app = AustialFactory.create(AloneModule, strict_modules=True)
    assert app.get(UsesModuleRef).ref is app.get(ModuleRef)


async def test_strict_mode_in_standalone_contexts() -> None:
    ctx = await AustialFactory.create_application_context(AppModule, strict_modules=True)
    assert isinstance(ctx.get(OrdersService), OrdersService)
    with pytest.raises(ModuleVisibilityError):
        ctx.get(StrangerService)


# -- app.select ----------------------------------------------------------------------------


def test_select_scopes_lookups_and_strict_get_checks_visibility() -> None:
    app = AustialFactory.create(AppModule)
    orders = app.select(OrdersModule)
    assert isinstance(orders.get(OrdersService), OrdersService)
    assert isinstance(orders.get(Mailer, strict=True), Mailer)  # exported by an imported module
    assert isinstance(orders.get(SharedClock, strict=True), SharedClock)  # global
    with pytest.raises(ModuleVisibilityError):
        orders.get(Secrets, strict=True)  # private to MailModule
    assert isinstance(orders.get(Secrets), Secrets)  # non-strict: the flat container finds it anyway
    assert app.select(AppModule).select(MailModule).module is MailModule
    with pytest.raises(KeyError, match="not part of"):
        app.select(type("Unknown", (), {}))


# -- graph ---------------------------------------------------------------------------------


def _graph() -> ModuleGraph:
    container = Container()
    scan_module(AppModule, container)
    return ModuleGraph(container.module_records, set(container.internal_tokens))


def test_graph_to_dict_describes_every_module() -> None:
    data = _graph().to_dict()
    by_name = {m["name"]: m for m in data["modules"]}
    assert set(by_name) == {
        "AppModule", "OrdersModule", "MailModule", "ClockModule", "SneakyModule",
        "OtherModule", "NotificationsModule", "ReexportConsumerModule",
    }  # fmt: skip
    orders = by_name["OrdersModule"]
    assert orders["imports"] == ["MailModule", "ClockModule"]
    assert orders["providers"] == ["OrdersService"] and orders["controllers"] == ["OrdersController"]
    assert by_name["MailModule"]["exports"] == ["Mailer"]
    assert by_name["ClockModule"]["global"] is True and by_name["MailModule"]["global"] is False
    json.dumps(data)  # serialisable


def test_graph_to_mermaid_lists_nodes_and_import_edges() -> None:
    text = _graph().to_mermaid()
    assert text.startswith("flowchart LR")
    assert "OrdersModule --> MailModule" in text and "AppModule --> OrdersModule" in text
    assert 'MailModule["MailModule' in text


def test_application_exposes_the_graph() -> None:
    app = AustialFactory.create(AppModule)
    assert {m["name"] for m in app.get_module_graph().to_dict()["modules"]} >= {"AppModule", "MailModule"}
