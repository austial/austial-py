"""``TimeoutInterceptor`` -- the classic Nest "timeout" interceptor recipe, built in::

    @UseInterceptors(TimeoutInterceptor(seconds=5))
    @Get("slow")
    async def slow(self): ...

Answers ``408 Request Timeout`` if the handler (and any interceptor inside this one) hasn't
finished in time. The handler is cancelled, so it must be ``async`` to be interruptible.
"""

from __future__ import annotations

import asyncio
from typing import Any

from austial.common.exceptions.http_exceptions import RequestTimeoutException
from austial.common.guards.base import ExecutionContext
from austial.common.interceptors.base import CallHandler, NestInterceptor


class TimeoutInterceptor(NestInterceptor):
    def __init__(self, seconds: float, message: str | None = None) -> None:
        self._seconds = seconds
        self._message = message

    async def intercept(self, context: ExecutionContext, next: CallHandler) -> Any:
        try:
            return await asyncio.wait_for(next.handle(), timeout=self._seconds)
        except TimeoutError:
            raise RequestTimeoutException(self._message or "Request timed out") from None
