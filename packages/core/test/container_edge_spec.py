"""DI container edge cases: provider shapes, defaults, optional deps, scope interplay, scanner
behaviour with dynamic modules."""

from __future__ import annotations

import pytest

from austial import (
    DynamicModule,
    Inject,
    Injectable,
    Module,
    Optional_,
    Scope,
)
from austial.core.container import Container, ProviderNotFoundError
from austial.core.module_scanner import scan_module


def test_invalid_provider_dict_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid provider"):
        Container().register({"provide": "X"})


def test_unregistered_non_class_token_reports_a_helpful_error() -> None:
    with pytest.raises(ProviderNotFoundError, match="NOPE"):
        Container().resolve("NOPE")


def test_unannotated_required_constructor_param_fails_loudly() -> None:
    class Bad:
        def __init__(self, mystery):  # no annotation, no default
            self.mystery = mystery

    with pytest.raises(ProviderNotFoundError, match="mystery"):
        Container().resolve(Bad)


def test_constructor_defaults_are_kept_for_types_the_container_does_not_provide() -> None:
    class Retrying:
        def __init__(self, retries: int = 3, label: str = "x", tags: list[str] | None = None):
            self.retries, self.label, self.tags = retries, label, tags

    instance = Container().resolve(Retrying)
    assert (instance.retries, instance.label, instance.tags) == (3, "x", None)


@Injectable()
class Dep:
    pass


class Needs:
    def __init__(self, dep: Dep | None = None, other: Dep = None):  # type: ignore[assignment]
        self.dep, self.other = dep, other


def test_defaulted_param_is_injected_when_its_type_is_provided() -> None:
    container = Container()
    container.register(Dep)
    needs = container.resolve(Needs)
    assert needs.other is container.resolve(Dep)  # `Dep`-typed + provided -> injected despite the default
    assert needs.dep is None  # a union type isn't a provider token -> default kept


@Injectable()
class Present:
    pass


class Absent:
    pass


class OptionalConsumer:
    def __init__(
        self,
        present: Present = Optional_(),  # type: ignore[assignment]
        absent: Absent = Optional_(),  # type: ignore[assignment]
    ):
        self.present, self.absent = present, absent


class MissingTokenConsumer:
    def __init__(self, thing=Inject("NOT-THERE")):
        self.thing = thing


def test_optional_marker_resolves_when_present_and_none_when_absent() -> None:
    container = Container()
    container.register(Present)
    consumer = container.resolve(OptionalConsumer)
    assert isinstance(consumer.present, Present)
    # `Absent` is a plain class, so the container auto-registers it rather than failing.
    assert isinstance(consumer.absent, Absent)

    with pytest.raises(ProviderNotFoundError):
        container.resolve(MissingTokenConsumer)


def test_factory_optional_dependency_becomes_none() -> None:
    container = Container()
    container.register(
        {
            "provide": "VALUE",
            "useFactory": lambda present, absent: (present, absent),
            "inject": ["PRESENT", {"token": "ABSENT", "optional": True}],
        }
    )
    container.register({"provide": "PRESENT", "useValue": 1})
    assert container.resolve("VALUE") == (1, None)

    broken = Container()
    broken.register({"provide": "V", "useFactory": lambda x: x, "inject": ["MISSING"]})
    with pytest.raises(ProviderNotFoundError):
        broken.resolve("V")


def test_factory_scope_transient_calls_factory_every_time() -> None:
    calls: list[int] = []

    def factory() -> int:
        calls.append(1)
        return len(calls)

    container = Container()
    container.register({"provide": "N", "useFactory": factory, "scope": Scope.TRANSIENT})
    assert (container.resolve("N"), container.resolve("N")) == (1, 2)

    once = Container()
    once.register({"provide": "N", "useFactory": lambda: object()})
    assert once.resolve("N") is once.resolve("N")


@Injectable(scope=Scope.REQUEST)
class ReqScoped:
    pass


@Injectable(scope=Scope.TRANSIENT)
class TransientHelper:
    def __init__(self, req: ReqScoped):
        self.req = req


@Injectable()
class ScopedConsumer:
    def __init__(self, helper: TransientHelper):
        self.helper = helper


def test_transient_depending_on_request_scoped_marks_its_consumers_request_bound() -> None:
    container = Container()
    for provider in (ReqScoped, TransientHelper, ScopedConsumer):
        container.register(provider)
    assert container.is_request_bound(ScopedConsumer)
    assert container.is_request_bound(TransientHelper)
    assert container.is_request_bound(ReqScoped)
    assert not container.is_request_bound(Dep)


def test_use_value_and_use_class_aliasing() -> None:
    @Injectable()
    class Base:
        pass

    @Injectable()
    class Impl(Base):
        pass

    container = Container()
    container.register({"provide": Base, "useClass": Impl})
    assert type(container.resolve(Base)) is Impl
    sentinel = object()
    container.register({"provide": "S", "useValue": sentinel})
    assert container.resolve("S") is sentinel


def test_set_instance_and_has() -> None:
    container = Container()
    obj = object()
    container.set_instance("X", obj)
    assert container.has("X") and container.resolve("X") is obj
    assert not container.has("Y")


# ---------------------------------------------------------------------------------------------
# module scanner
# ---------------------------------------------------------------------------------------------


def test_scanner_rejects_a_class_that_is_not_a_module() -> None:
    class NotAModule:
        pass

    with pytest.raises(TypeError, match="not decorated"):
        scan_module(NotAModule, Container())


def test_scanner_handles_circular_module_imports_and_records_dependency_order() -> None:
    from austial import forward_ref

    @Injectable()
    class AService:
        pass

    @Injectable()
    class BService:
        pass

    @Module(imports=[forward_ref(lambda: BModule)], providers=[AService])
    class AModule:
        pass

    @Module(imports=[forward_ref(lambda: AModule)], providers=[BService])
    class BModule:
        pass

    container = Container()
    result = scan_module(AModule, container)
    assert [r.module for r in result.records] == [BModule, AModule]  # imports first
    assert set(result.modules) == {AModule, BModule}
    assert container.resolve(AService) is not None and container.resolve(BService) is not None


def test_scanner_merges_dynamic_module_providers_with_static_ones() -> None:
    @Injectable()
    class Static:
        pass

    @Module(providers=[Static])
    class Configurable:
        pass

    dynamic = DynamicModule(module=Configurable, providers=[{"provide": "EXTRA", "useValue": 1}])
    container = Container()
    result = scan_module(Module(imports=[dynamic])(type("Root", (), {})), container)
    record = next(r for r in result.records if r.module is Configurable)
    assert Static in record.providers and "EXTRA" in record.providers
    assert container.resolve("EXTRA") == 1


def test_scanner_registers_controllers_from_dynamic_modules() -> None:
    from austial import Controller, Get

    @Controller("dyn")
    class DynController:
        @Get()
        async def get(self): ...

    container = Container()
    dynamic = DynamicModule(module=None, controllers=[DynController])
    result = scan_module(Module(imports=[dynamic])(type("Root2", (), {})), container)
    assert result.controllers == [DynController]
    assert container.controllers == [DynController]
