"""Shared "find the right exception filter and call it" logic, used both
inside route handlers (:mod:`austial.core.router_builder`) and as the
application-level fallback for errors FastAPI itself raises before a route
handler ever runs (e.g. request validation failures)."""

from __future__ import annotations

from collections.abc import Sequence

from starlette.requests import Request
from starlette.responses import Response

from austial.common.filters.base import ArgumentsHost
from austial.core.metadata import CATCH_METADATA, get_metadata


async def dispatch_exception(exc: BaseException, request: Request, filters: Sequence) -> Response:
    host = ArgumentsHost(request)
    for exception_filter in filters:
        catch_types = get_metadata(CATCH_METADATA, type(exception_filter), ())
        if not catch_types or isinstance(exc, catch_types):
            return await exception_filter.catch(exc, host)
    raise exc
