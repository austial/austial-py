"""``NestMiddleware`` + ``MiddlewareConsumer`` -- mirrors ``@nestjs/common``.

A module opts into middleware by defining a ``configure(self, consumer)``
method (mirroring Nest's ``NestModule`` interface)::

    class AppModule:
        def configure(self, consumer: MiddlewareConsumer) -> None:
            consumer.apply(LoggingMiddleware).for_routes("*")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from starlette.requests import Request
from starlette.responses import Response


class NestMiddleware(ABC):
    @abstractmethod
    async def use(self, request: Request, call_next: Callable[[], Awaitable[Response]]) -> Response:
        raise NotImplementedError


@dataclass
class MiddlewareBinding:
    middlewares: Sequence[Any]
    routes: Sequence[str]

    def matches(self, path: str) -> bool:
        for route in self.routes:
            if route in ("*", "(.*)"):
                return True
            if path == route or path.startswith(route.rstrip("*")):
                return True
        return False


class _RouteBinder:
    def __init__(self, consumer: MiddlewareConsumer, middlewares: Sequence[Any]):
        self._consumer = consumer
        self._middlewares = middlewares

    def for_routes(self, *routes: str) -> MiddlewareConsumer:
        self._consumer.bindings.append(MiddlewareBinding(middlewares=self._middlewares, routes=routes or ("*",)))
        return self._consumer


class MiddlewareConsumer:
    """Passed into a module's ``configure()`` hook; collects
    ``apply(...).for_routes(...)`` bindings for the factory to wire up."""

    def __init__(self):
        self.bindings: list[MiddlewareBinding] = []

    def apply(self, *middlewares: Any) -> _RouteBinder:
        return _RouteBinder(self, middlewares)
