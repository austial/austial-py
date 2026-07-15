"""``@Controller()`` and HTTP method decorators -- mirrors ``@nestjs/common``."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from austial.core.metadata import (
    CONTROLLER_METADATA,
    HEADER_METADATA,
    HTTP_CODE_METADATA,
    ROUTE_METADATA,
    set_metadata,
)

T = TypeVar("T")

_EXPRESS_PARAM_RE = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")


def _to_fastapi_path(path: str) -> str:
    """Translates Nest/Express-style ``:id`` path params into FastAPI/Starlette's
    ``{id}`` syntax, so route paths can be written exactly like in Nest, e.g.
    ``@Get(":id")`` or ``@Get("users/:id/posts/:postId")``."""
    return _EXPRESS_PARAM_RE.sub(r"{\1}", path)


@dataclass
class ControllerMetadata:
    prefix: str = ""
    tags: list | None = None


@dataclass
class RouteMetadata:
    method: str
    path: str = ""


def Controller(prefix: str = "", *, tags: list | None = None) -> Callable[[T], T]:
    """Class decorator: declares a controller and its route prefix.

    Example::

        @Controller("health")
        class HealthController:
            def __init__(self, health_service: HealthService):
                self.health_service = health_service

            @Get()
            async def check(self):
                ...
    """
    prefix = "/" + prefix.strip("/") if prefix else ""

    def decorator(cls: T) -> T:
        set_metadata(CONTROLLER_METADATA, ControllerMetadata(prefix=prefix, tags=tags))(cls)
        return cls

    return decorator


def _route_decorator(method: str):
    def factory(path: str = "") -> Callable:
        path = _to_fastapi_path(path)
        normalized = "/" + path.strip("/") if path else ""

        def decorator(fn):
            set_metadata(ROUTE_METADATA, RouteMetadata(method=method, path=normalized))(fn)
            return fn

        return decorator

    return factory


Get = _route_decorator("GET")
Post = _route_decorator("POST")
Put = _route_decorator("PUT")
Patch = _route_decorator("PATCH")
Delete = _route_decorator("DELETE")
Options = _route_decorator("OPTIONS")
Head = _route_decorator("HEAD")


def HttpCode(status_code: int) -> Callable:
    """Method decorator overriding the default 2xx status code, mirrors
    Nest's ``@HttpCode()``."""

    def decorator(fn):
        set_metadata(HTTP_CODE_METADATA, status_code)(fn)
        return fn

    return decorator


def Header(key: str, value: str) -> Callable:
    """Method decorator adding a static response header, mirrors Nest's ``@Header()``.
    Stackable -- multiple ``@Header`` calls accumulate."""

    def decorator(fn):
        headers: dict[str, str] = dict(getattr(fn, "__austial_metadata__", {}).get(HEADER_METADATA, {}))
        headers[key] = value
        set_metadata(HEADER_METADATA, headers)(fn)
        return fn

    return decorator
