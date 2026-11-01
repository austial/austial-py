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

from typing import Any

from fastapi import Body as _Body
from fastapi import Header as _Header
from fastapi import Path as _Path
from fastapi import Query as _Query
from fastapi import Request as Req  # noqa: F401  (re-export, Nest-style alias)
from fastapi import Response as Res  # noqa: F401  (re-export, Nest-style alias)


def Param(name: str | None = None, *, default: Any = ..., **kwargs) -> Any:
    """Equivalent to Nest's ``@Param('id')``: binds a path parameter."""
    return _Path(default=default, alias=name, **kwargs)


def Query(name: str | None = None, *, default: Any = None, **kwargs) -> Any:
    """Equivalent to Nest's ``@Query('search')``: binds a query-string parameter."""
    return _Query(default=default, alias=name, **kwargs)


def Body(*, default: Any = ..., embed: bool = False, **kwargs) -> Any:
    """Equivalent to Nest's ``@Body()``: binds (and, via pydantic, validates)
    the request body against the parameter's type annotation."""
    return _Body(default=default, embed=embed, **kwargs)


def Headers(name: str | None = None, *, default: Any = None, **kwargs) -> Any:
    """Equivalent to Nest's ``@Headers('x-api-key')``: binds a request header."""
    return _Header(default=default, alias=name, **kwargs)


class GuardStateMarker:
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


def FromRequestState(attribute: str, *, default: Any = None) -> Any:  # noqa: N802 - decorator-style naming
    """Bind a handler parameter to ``request.state.<attribute>``, resolved after every guard for
    this route has run. ``AuthGuard`` populates ``state.user``, ``TenantGuard`` populates
    ``state.tenant``; a product guard may publish its own. Missing state resolves to ``default``
    (e.g. on a ``@Public()`` route no guard ran)."""
    return GuardStateMarker(attribute, default=default)
