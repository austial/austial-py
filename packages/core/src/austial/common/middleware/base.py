"""``NestMiddleware`` + ``MiddlewareConsumer`` -- mirrors ``@nestjs/common``.

A module opts into middleware by defining a ``configure(self, consumer)``
method (mirroring Nest's ``NestModule`` interface)::

    class AppModule:
        def configure(self, consumer: MiddlewareConsumer) -> None:
            consumer.apply(LoggingMiddleware).for_routes("*")
            consumer.apply(AuthMiddleware).exclude(
                "health", RouteInfo("login", RequestMethod.POST)
            ).for_routes(CatsController)
            consumer.apply(request_timer).for_routes("/api*")  # a plain async function works too

Targets for ``for_routes`` / ``exclude`` may be a path string (``"/cats"`` exact or under it,
``"/cats*"`` prefix, ``"*"`` everything), a :class:`RouteInfo` (path + method) or a controller
class (every route under its prefix; the global prefix is not part of the match).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from austial.common.enums import RequestMethod, RouteInfo
from austial.core.metadata import CONTROLLER_METADATA, get_metadata

RouteTarget = Any  # str | RouteInfo | type


class NestMiddleware(ABC):
    """Subclass and implement ``async def use(self, request, call_next)``. ``call_next()`` runs the
    rest of the chain and returns the response."""

    @abstractmethod
    async def use(self, request: Request, call_next: Callable[[], Awaitable[Response]]) -> Response:
        raise NotImplementedError


class _FunctionMiddleware(NestMiddleware):
    """Adapts ``async def fn(request, call_next)`` to the class-based interface."""

    def __init__(self, fn: Callable[..., Awaitable[Response]]):
        self._fn = fn

    async def use(self, request: Request, call_next: Callable[[], Awaitable[Response]]) -> Response:
        return await self._fn(request, call_next)


def _normalize_path(path: str) -> str:
    return "/" + path.strip("/") if path.strip("/") else "/"


def _target_matches(target: RouteTarget, path: str, method: str) -> bool:
    if isinstance(target, RouteInfo):
        wanted = target.method
        return (wanted == RequestMethod.ALL or wanted == method) and _path_matches(target.path, path)
    if isinstance(target, type):
        meta = get_metadata(CONTROLLER_METADATA, target)
        prefix = getattr(meta, "prefix", "") or ""
        return not prefix or path == prefix or path.startswith(prefix + "/")
    return _path_matches(str(target), path)


def _path_matches(pattern: str, path: str) -> bool:
    if pattern in ("*", "(.*)", "/*"):
        return True
    if pattern.endswith("*"):
        return path.startswith(_normalize_path(pattern.rstrip("*")).rstrip("/") or "/")
    normalized = _normalize_path(pattern)
    return path == normalized or path.startswith(normalized + "/")


@dataclass
class MiddlewareBinding:
    middlewares: Sequence[Any]
    routes: Sequence[RouteTarget]
    excludes: Sequence[RouteTarget] = field(default_factory=tuple)

    def matches(self, path: str, method: str = "GET") -> bool:
        if any(_target_matches(target, path, method) for target in self.excludes):
            return False
        return any(_target_matches(target, path, method) for target in self.routes)


class _RouteBinder:
    def __init__(self, consumer: MiddlewareConsumer, middlewares: Sequence[Any]):
        self._consumer = consumer
        self._middlewares = [self._adapt(m) for m in middlewares]
        self._excludes: list[RouteTarget] = []

    @staticmethod
    def _adapt(middleware: Any) -> Any:
        if isinstance(middleware, type) or hasattr(middleware, "use"):
            return middleware
        if callable(middleware):
            return _FunctionMiddleware(middleware)
        raise TypeError(f"Not a middleware: {middleware!r}")

    def exclude(self, *routes: RouteTarget) -> _RouteBinder:
        """Routes the middleware must skip even if ``for_routes`` matches them."""
        self._excludes.extend(routes)
        return self

    def for_routes(self, *routes: RouteTarget) -> MiddlewareConsumer:
        binding = MiddlewareBinding(
            middlewares=self._middlewares, routes=routes or ("*",), excludes=tuple(self._excludes)
        )
        self._consumer.bindings.append(binding)
        return self._consumer


class MiddlewareConsumer:
    """Passed into a module's ``configure()`` hook; collects
    ``apply(...).for_routes(...)`` bindings for the factory to wire up."""

    def __init__(self):
        self.bindings: list[MiddlewareBinding] = []

    def apply(self, *middlewares: Any) -> _RouteBinder:
        return _RouteBinder(self, middlewares)
