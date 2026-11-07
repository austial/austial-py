"""``@Next()`` -- mirrors Nest's: let a handler *decline* a request so the next matching route handles it.

::

    @Controller("files")
    class CacheFirst:
        @Get(":name")
        async def cached(self, name: str, next=Next()):
            if name not in CACHE:
                return next()          # hand over to the next route registered for GET /files/:name
            return CACHE[name]

    @Controller("files")
    class Origin:
        @Get(":name")
        async def origin(self, name: str): ...

Routes are tried in registration order. If every remaining match also declines (or none matches) the request gets the
normal ``404``. Guards, pipes and interceptors have already run for the route that declined, and the next route runs
its own. The request body is read once and replayed for the next route.
"""

from __future__ import annotations

from typing import NoReturn


class PassToNext(BaseException):  # noqa: N818
    """Raised by ``next()``. A ``BaseException`` on purpose: filters and ``except Exception`` blocks in handlers and
    interceptors must not swallow it."""


class NextFunction:
    def __call__(self) -> NoReturn:
        raise PassToNext
