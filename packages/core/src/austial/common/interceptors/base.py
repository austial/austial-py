"""``NestInterceptor`` + ``CallHandler`` -- mirrors ``@nestjs/common``.

Nest interceptors wrap an RxJS ``Observable``; Austial has no RxJS, so
``CallHandler.handle()`` is simply an ``async`` continuation representing
"run the rest of the pipeline (further interceptors, then the handler) and
give me its return value". Interceptors can inspect/replace the result, time
the call, catch+rethrow, etc. -- same capabilities, async/await shaped.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from austial.common.guards.base import ExecutionContext


class CallHandler:
    def __init__(self, next_call: Callable[[], Awaitable[Any]]):
        self._next_call = next_call

    async def handle(self) -> Any:
        return await self._next_call()


class NestInterceptor(ABC):
    @abstractmethod
    async def intercept(self, context: ExecutionContext, next: CallHandler) -> Any:
        raise NotImplementedError
