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
