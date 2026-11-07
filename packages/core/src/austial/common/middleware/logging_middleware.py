"""``LoggingMiddleware`` -- the canonical Nest "log every request" example
(nestjs.com/docs/middleware uses the exact same one, just in TypeScript)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

from austial.common.logger import Logger
from austial.common.middleware.base import NestMiddleware

_logger = Logger("HTTP")


class LoggingMiddleware(NestMiddleware):
    async def use(self, request: Request, call_next: Callable[[], Awaitable[Response]]) -> Response:
        start = time.perf_counter()
        response = await call_next()
        duration_ms = (time.perf_counter() - start) * 1000
        _logger.log(f"{request.method} {request.url.path} {response.status_code} - {duration_ms:.1f}ms")
        return response
