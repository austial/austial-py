"""``@Controller()`` and HTTP method decorators -- mirrors ``@nestjs/common``."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from austial.core.metadata import (
    CONTROLLER_METADATA,
    HEADER_METADATA,
    HTTP_CODE_METADATA,
    REDIRECT_METADATA,
    RENDER_METADATA,
    ROUTE_METADATA,
    SSE_METADATA,
    VERSION_METADATA,
    set_metadata,
)

T = TypeVar("T")

_EXPRESS_PARAM_RE = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)(\*)?")


def _to_fastapi_path(path: str) -> str:
    """Translates Nest/Express-style ``:id`` path params into FastAPI/Starlette's
    ``{id}`` syntax, so route paths can be written exactly like in Nest, e.g.
    ``@Get(":id")`` or ``@Get("users/:id/posts/:postId")``.

    A trailing ``*`` on a param (``:key*``) marks it as a catch-all that also
    matches ``/``, translated to FastAPI's ``{key:path}`` converter instead of
    the plain ``{key}`` -- e.g. ``@Get("files/:key*")`` captures ``a/b/c.pdf``
    as a single ``key`` value. Substituted in one pass (rather than a separate
    wildcard-then-plain pass) because FastAPI's own ``{key:path}`` syntax
    contains a colon that a second plain-``:name`` pass would re-match and
    corrupt.
    """
    return _EXPRESS_PARAM_RE.sub(lambda m: f"{{{m.group(1)}:path}}" if m.group(2) else f"{{{m.group(1)}}}", path)


@dataclass
class ControllerMetadata:
    prefix: str = ""
    tags: list | None = None
    version: str | list[str] | None = None
    host: str | list[str] | None = None


@dataclass
class RouteMetadata:
    method: str
    path: str = ""


def Controller(
    prefix: str = "",
    *,
    tags: list | None = None,
    version: str | Sequence[str] | None = None,
    host: str | Sequence[str] | None = None,
) -> Callable[[T], T]:
    """Class decorator: declares a controller and its route prefix.

    ``version`` pins every route of the controller to an API version (see ``app.enable_versioning``;
    a route's own ``@Version`` overrides it). ``host`` restricts it to requests for a matching
    ``Host`` header -- a ``:name`` segment captures a value, readable with ``HostParam("name")``,
    e.g. ``@Controller("admin", host=":tenant.example.com")``.

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
        meta = ControllerMetadata(prefix=prefix, tags=tags, version=_as_versions(version), host=_as_hosts(host))
        set_metadata(CONTROLLER_METADATA, meta)(cls)
        return cls

    return decorator


def _as_versions(version: str | Sequence[str] | None) -> str | list[str] | None:
    if version is None:
        return None
    return str(version) if isinstance(version, str) else [str(v) for v in version]


def _as_hosts(host: str | Sequence[str] | None) -> str | list[str] | None:
    if host is None:
        return None
    return host if isinstance(host, str) else list(host)


def _route_decorator(method: str):
    def factory(path: str = "") -> Callable:
        path = _to_fastapi_path(path)
        normalized = "/" + path.strip("/") if path else ""

        def decorator(fn):
            set_metadata(ROUTE_METADATA, RouteMetadata(method=method, path=normalized))(fn)
            return fn

        return decorator

    return factory


All = _route_decorator("ALL")
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


def Version(version: str | Sequence[str]) -> Callable:  # noqa: N802 - mirrors Nest
    """Method decorator pinning one route to an API version (or several: ``@Version(["1", "2"])``),
    overriding the controller's. ``@Version(VERSION_NEUTRAL)`` serves it whatever version (or none)
    the request names. Needs ``app.enable_versioning(...)``."""

    def decorator(fn):
        set_metadata(VERSION_METADATA, _as_versions(version))(fn)
        return fn

    return decorator


def Redirect(url: str = "", status_code: int = 302) -> Callable:  # noqa: N802
    """Method decorator answering with a redirect, mirrors Nest's ``@Redirect()``. The handler may
    return ``{"url": ..., "status_code": ...}`` to pick the target at runtime."""

    def decorator(fn):
        set_metadata(REDIRECT_METADATA, {"url": url, "status_code": status_code})(fn)
        return fn

    return decorator


def Render(template: str) -> Callable:  # noqa: N802
    """Method decorator rendering a Jinja2 template with the dict the handler returns, mirrors Nest's
    ``@Render()``. Needs ``app.set_base_views_dir("views")``::

        @Get()
        @Render("index.html")
        async def home(self):
            return {"title": "Hello"}
    """

    def decorator(fn):
        set_metadata(RENDER_METADATA, template)(fn)
        return fn

    return decorator


def Sse(path: str = "") -> Callable:  # noqa: N802
    """Method decorator for a Server-Sent Events endpoint, mirrors Nest's ``@Sse()``. The handler
    returns an (async) iterable of events: a ``MessageEvent``, a dict with ``data`` (and optional
    ``id``/``event``/``retry``), or any value (sent as ``data``)."""
    get = _route_decorator("GET")(path)

    def decorator(fn):
        get(fn)
        set_metadata(SSE_METADATA, True)(fn)
        return fn

    return decorator
