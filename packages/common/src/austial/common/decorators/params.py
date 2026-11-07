"""Parameter helpers -- mirrors Nest's ``@Param()``/``@Query()``/``@Body()``/etc.

Python has no parameter decorators, so instead of annotating the parameter,
these are used as **default values** in the handler signature, e.g.::

    @Get(":id")
    async def find_one(self, id: str = Param("id")):
        ...

    @Post()
    async def create(self, dto: CreateCatDto = Body()):
        ...

Under the hood these simply return FastAPI's own ``Path``/``Query``/``Body``/
``Header`` markers, since FastAPI + pydantic already do exactly what Nest's
param decorators + ``ValidationPipe`` do. ``Req``/``Res`` are just re-exports
of Starlette's ``Request``/``Response`` for type-hinting convenience.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from fastapi import Body as _Body
from fastapi import File as _File
from fastapi import Header as _Header
from fastapi import Path as _Path
from fastapi import Query as _Query
from fastapi import Request as Req  # noqa: F401  (re-export, Nest-style alias)
from fastapi import Response as Res  # noqa: F401  (re-export, Nest-style alias)
from fastapi import params as _fastapi_params

# Pipes attached to one parameter (`Param("id", ParseIntPipe)`). FastAPI's marker objects can't carry
# extra attributes, so they're kept here keyed by the marker's identity -- the marker lives as long as
# the handler's signature default does, which is exactly how long the router builder needs the entry.
_PARAM_PIPES: dict[int, tuple] = {}


def _with_pipes(marker: Any, pipes: tuple) -> Any:
    if pipes:
        _PARAM_PIPES[id(marker)] = pipes
    return marker


def get_param_pipes(marker: Any) -> tuple:
    """The pipes attached to a ``Param``/``Query``/``Body``/``Headers``/``UploadedFile`` marker."""
    return _PARAM_PIPES.get(id(marker), ())


def param_kind(marker: Any) -> str:
    """Nest's ``ArgumentMetadata.type`` for a parameter marker."""
    if isinstance(marker, _fastapi_params.Path):
        return "param"
    if isinstance(marker, _fastapi_params.Query):
        return "query"
    if isinstance(marker, _fastapi_params.Body):
        return "body"
    return "custom"


def is_raw_string_param(marker: Any) -> bool:
    """True for a ``Param``/``Query``/``Headers`` marker that has pipes attached: the router then
    hands FastAPI a ``str`` annotation, so the pipes receive the raw text and do the parsing."""
    return id(marker) in _PARAM_PIPES and isinstance(
        marker, _fastapi_params.Path | _fastapi_params.Query | _fastapi_params.Header
    )


def Param(name: str | None = None, *pipes: Any, default: Any = ..., **kwargs) -> Any:
    """Equivalent to Nest's ``@Param('id', ParseIntPipe)``: binds a path parameter, optionally
    running it through ``pipes`` (classes or instances) before it reaches the handler."""
    return _with_pipes(_Path(default=default, alias=name, **kwargs), pipes)


def Query(name: str | None = None, *pipes: Any, default: Any = None, **kwargs) -> Any:
    """Equivalent to Nest's ``@Query('search', pipes...)``: binds a query-string parameter."""
    return _with_pipes(_Query(default=default, alias=name, **kwargs), pipes)


def Body(*pipes: Any, default: Any = ..., embed: bool = False, **kwargs) -> Any:
    """Equivalent to Nest's ``@Body()``: binds (and, via pydantic, validates)
    the request body against the parameter's type annotation."""
    return _with_pipes(_Body(default=default, embed=embed, **kwargs), pipes)


def Headers(name: str | None = None, *pipes: Any, default: Any = None, **kwargs) -> Any:
    """Equivalent to Nest's ``@Headers('x-api-key')``: binds a request header."""
    return _with_pipes(_Header(default=default, alias=name, **kwargs), pipes)


def UploadedFile(name: str = "file", *pipes: Any, default: Any = ..., **kwargs) -> Any:
    """Equivalent to Nest's ``@UploadedFile()``: binds one multipart file field. Annotate the
    parameter ``UploadFile`` (``UploadFile | None`` with ``default=None`` for an optional one) and
    add ``ParseFilePipe(...)`` to validate size/type."""
    return _with_pipes(_File(default=default, alias=name, **kwargs), pipes)


def UploadedFiles(name: str = "files", *pipes: Any, default: Any = ..., **kwargs) -> Any:
    """Equivalent to Nest's ``@UploadedFiles()``: binds a repeated multipart field; annotate the
    parameter ``list[UploadFile]``."""
    return _with_pipes(_File(default=default, alias=name, **kwargs), pipes)


class DeferredParam:
    """Base for handler parameters filled in by the router *after every guard has run*, from the
    :class:`~austial.common.guards.base.ExecutionContext` -- unlike ``Param``/``Query``/``Body``,
    which FastAPI resolves up front. Subclass and implement :meth:`resolve`."""

    async def resolve(self, context: Any) -> Any:  # pragma: no cover - interface
        raise NotImplementedError


class GuardStateMarker(DeferredParam):
    """Marks a handler parameter whose value must come from ``request.state`` *after every guard
    has run* -- unlike every other param helper above, which FastAPI resolves as an ordinary
    dependency before the handler (and therefore before the router's own guard loop, which runs
    inside the handler's wrapper). A plain ``Depends(lambda request: request.state.user)`` would
    read an empty ``state`` for exactly that reason.

    ``RouterBuilder._build_endpoint`` special-cases this marker: it is excluded from what FastAPI
    sees (it has no place in the OpenAPI schema -- it never comes from the wire) and is instead
    populated from ``request.state`` right after the guard loop succeeds. See
    ``austial.auth.CurrentUser()`` for the canonical use.
    """

    __slots__ = ("attribute", "default")

    def __init__(self, attribute: str, *, default: Any = None) -> None:
        self.attribute = attribute
        self.default = default

    async def resolve(self, context: Any) -> Any:
        return getattr(context.get_request().state, self.attribute, self.default)


def FromRequestState(attribute: str, *, default: Any = None) -> Any:  # noqa: N802 - decorator-style naming
    """Bind a handler parameter to ``request.state.<attribute>``, resolved after every guard for
    this route has run. ``AuthGuard`` populates ``state.user``, ``TenantGuard`` populates
    ``state.tenant``; a product guard may publish its own. Missing state resolves to ``default``
    (e.g. on a ``@Public()`` route no guard ran)."""
    return GuardStateMarker(attribute, default=default)


class _RequestValueMarker(DeferredParam):
    def __init__(self, extract: Callable[[Any], Any]) -> None:
        self._extract = extract

    async def resolve(self, context: Any) -> Any:
        return self._extract(context.get_request())


def Ip() -> Any:  # noqa: N802 - decorator-style naming
    """Equivalent to Nest's ``@Ip()``: the client's address. Behind a reverse proxy, call
    ``app.set_trust_proxy()`` so it reflects ``X-Forwarded-For`` instead of the proxy."""
    return _RequestValueMarker(lambda request: request.client.host if request.client else None)


def HostParam(name: str | None = None) -> Any:  # noqa: N802
    """Equivalent to Nest's ``@HostParam('account')``: a value captured by the controller's host
    pattern (``@Controller(host=":account.example.com")``); no name returns all of them as a dict."""

    def extract(request: Any) -> Any:
        params = request.scope.get("austial.host_params", {})
        return params if name is None else params.get(name)

    return _RequestValueMarker(extract)


def Session(name: str | None = None) -> Any:  # noqa: N802
    """Equivalent to Nest's ``@Session()``: the session dict (or one key of it). Needs Starlette's
    ``SessionMiddleware`` -- ``app.use(SessionMiddleware, secret_key=...)``."""

    def extract(request: Any) -> Any:
        session = request.session
        return session if name is None else session.get(name)

    return _RequestValueMarker(extract)


class _CustomParamMarker(DeferredParam):
    def __init__(self, factory: Callable[..., Any], data: Any) -> None:
        self._factory = factory
        self._data = data

    async def resolve(self, context: Any) -> Any:
        result = self._factory(self._data, context)
        return await result if inspect.isawaitable(result) else result


def create_param_decorator(factory: Callable[[Any, Any], Any]) -> Callable[..., Any]:
    """Mirrors Nest's ``createParamDecorator``. ``factory(data, context)`` (sync or async) receives
    whatever was passed at the call site plus the :class:`ExecutionContext`::

        CurrentUser = create_param_decorator(lambda key, ctx: ctx.get_request().state.user[key])

        @Get("me")
        async def me(self, user_id=CurrentUser("id")): ...
    """

    def decorator(data: Any = None) -> Any:
        return _CustomParamMarker(factory, data)

    return decorator
