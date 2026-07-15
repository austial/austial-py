"""``TransformInterceptor`` -- the canonical Nest "wrap every response" example.

Wraps every successful controller response in a ``{"data": ..., "timestamp": ...}``
envelope, exactly like the interceptor from the official NestJS docs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from austial.common.guards.base import ExecutionContext
from austial.common.interceptors.base import CallHandler, NestInterceptor


class TransformInterceptor(NestInterceptor):
    async def intercept(self, context: ExecutionContext, next: CallHandler) -> Any:
        result = await next.handle()
        return {"data": result, "timestamp": datetime.now(UTC).isoformat()}
