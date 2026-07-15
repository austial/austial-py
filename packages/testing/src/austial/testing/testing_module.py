"""``Test.create_testing_module(...).compile()`` -- mirrors ``@nestjs/testing``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI

from austial.common.decorators.modules import Module
from austial.core.app import AustialApplication
from austial.core.container import Container
from austial.core.module_scanner import scan_module


class TestingModule:
    def __init__(self, container: Container, controllers: list):
        self._container = container
        self._controllers = controllers

    def get(self, token: Any) -> Any:
        """Fetches a resolved provider straight out of the DI container --
        the whole point of testing modules: unit-test a service with its real
        dependency graph, no manual mocking wiring required."""
        return self._container.resolve(token)

    def create_austial_application(self) -> AustialApplication:
        """Mirrors ``moduleRef.createNestApplication()``. Call ``await app.init()``
        before making requests against it."""
        fastapi_app = FastAPI(title="Austial (test)")
        return AustialApplication(self._container, fastapi_app, self._controllers, [])


class TestingModuleBuilder:
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

    async def compile(self) -> TestingModule:
        container = Container()
        scan_result = scan_module(self._root_module, container)
        return TestingModule(container, scan_result.controllers)


class Test:
    """Entry point, mirrors Nest's ``Test.createTestingModule({...})``."""

    @staticmethod
    def create_testing_module(
        *,
        imports: Sequence[Any] = (),
        controllers: Sequence[type] = (),
        providers: Sequence[Any] = (),
    ) -> TestingModuleBuilder:
        return TestingModuleBuilder(imports=imports, controllers=controllers, providers=providers)
