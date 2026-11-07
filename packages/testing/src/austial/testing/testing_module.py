"""``Test.create_testing_module(...).compile()`` -- mirrors ``@nestjs/testing``.

Override anything before compiling -- providers, guards, pipes, interceptors, filters -- and
stub whatever you didn't register with ``use_mocker``::

    module = await (
        Test.create_testing_module(imports=[CatsModule])
        .override_provider(CatsRepository).use_value(FakeCatsRepository())
        .override_guard(AuthGuard).use_class(AllowAllGuard)
        .use_mocker(lambda token: MagicMock())
        .compile()
    )
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from fastapi import FastAPI

from austial.common.decorators.modules import Module
from austial.core.app import AustialApplication
from austial.core.container import Container
from austial.core.module_scanner import scan_module
from austial.core.request_context import ContextId


class TestingModule:
    __test__ = False  # not a pytest test class, despite the name

    def __init__(self, container: Container, controllers: list):
        self._container = container
        self._controllers = controllers

    def get(self, token: Any) -> Any:
        """Fetches a resolved provider straight out of the DI container --
        the whole point of testing modules: unit-test a service with its real
        dependency graph, no manual mocking wiring required."""
        return self._container.resolve(token)

    def resolve(self, token: Any, context_id: ContextId | None = None) -> Any:
        """Like :meth:`get`, but also builds request-scoped providers (inside ``context_id``)."""
        from austial.core.module_ref import ModuleRef

        return self._container.resolve(ModuleRef).resolve(token, context_id)

    def create_austial_application(self) -> AustialApplication:
        """Mirrors ``moduleRef.createNestApplication()``. Call ``await app.init()``
        before making requests against it."""
        fastapi_app = FastAPI(title="Austial (test)")
        return AustialApplication(self._container, fastapi_app, self._controllers, [])

    async def close(self) -> None:
        """Runs the termination lifecycle hooks, like ``await moduleRef.close()``."""
        await self._container.lifecycle.run_destroy()
        self._container.lifecycle.reset()


class OverrideBy:
    """What to replace a token with: ``use_value``, ``use_class`` or ``use_factory``."""

    def __init__(self, builder: TestingModuleBuilder, token: Any):
        self._builder = builder
        self._token = token

    def use_value(self, value: Any) -> TestingModuleBuilder:
        return self._builder._add_override({"provide": self._token, "useValue": value})  # noqa: SLF001

    def use_class(self, cls: type) -> TestingModuleBuilder:
        return self._builder._add_override({"provide": self._token, "useClass": cls})  # noqa: SLF001

    def use_factory(self, factory: Callable[..., Any], inject: Sequence[Any] = ()) -> TestingModuleBuilder:
        override = {"provide": self._token, "useFactory": factory, "inject": list(inject)}
        return self._builder._add_override(override)  # noqa: SLF001


class TestingModuleBuilder:
    __test__ = False

    def __init__(
        self,
        *,
        imports: Sequence[Any] = (),
        controllers: Sequence[type] = (),
        providers: Sequence[Any] = (),
    ):
        @Module(imports=list(imports), controllers=list(controllers), providers=list(providers))
        class _TestingRootModule:
            pass

        self._root_module = _TestingRootModule
        self._overrides: list[dict[str, Any]] = []
        self._mocker: Callable[[Any], Any] | None = None

    def _add_override(self, definition: dict[str, Any]) -> TestingModuleBuilder:
        self._overrides.append(definition)
        return self

    def override_provider(self, token: Any) -> OverrideBy:
        """Replace the provider registered under ``token`` (a class or any other token)."""
        return OverrideBy(self, token)

    # Guards, pipes, interceptors and filters are resolved from the container by their class, so
    # overriding one is overriding that provider -- the aliases just read better in a test.
    override_guard = override_provider
    override_pipe = override_provider
    override_interceptor = override_provider
    override_filter = override_provider

    def use_mocker(self, mocker: Callable[[Any], Any]) -> TestingModuleBuilder:
        """``mocker(token)`` supplies a stand-in for every dependency nothing registered; return
        ``None`` to leave a token to the container's normal handling."""
        self._mocker = mocker
        return self

    async def compile(self) -> TestingModule:
        container = Container()
        container.mocker = self._mocker
        scan_result = scan_module(self._root_module, container)
        for override in self._overrides:
            container.register(override)
        await container.init_async_providers()
        return TestingModule(container, scan_result.controllers)


class Test:
    """Entry point, mirrors Nest's ``Test.createTestingModule({...})``."""

    __test__ = False

    @staticmethod
    def create_testing_module(
        *,
        imports: Sequence[Any] = (),
        controllers: Sequence[type] = (),
        providers: Sequence[Any] = (),
    ) -> TestingModuleBuilder:
        return TestingModuleBuilder(imports=imports, controllers=controllers, providers=providers)
