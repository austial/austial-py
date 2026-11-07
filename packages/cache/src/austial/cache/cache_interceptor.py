"""``CacheInterceptor`` -- caches the responses of ``GET`` handlers, mirrors Nest's.

::

    @Controller("cats")
    @UseInterceptors(CacheInterceptor)      # a class: resolved from DI, so it gets the CacheService
    class CatsController:
        @Get()
        @CacheTTL(30)
        async def find_all(self): ...

        @Get("featured")
        @CacheKey("featured-cats")
        async def featured(self): ...

Register it for the whole app with ``{"provide": APP_INTERCEPTOR, "useClass": CacheInterceptor}``.

Responses are cached as the handler returned them, and the same object is handed back on a hit:
treat cached values as immutable. Streamed/raw ``Response`` results and non-``GET`` requests are never
cached. Override :meth:`track_by` to key by something other than the URL (e.g. per user).
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from austial.cache.cache_service import CacheService
from austial.cache.decorators import CACHE_KEY_METADATA, CACHE_TTL_METADATA
from austial.common.file.streamable_file import StreamableFile
from austial.common.guards.base import ExecutionContext
from austial.common.interceptors.base import CallHandler, NestInterceptor
from austial.core.metadata import get_metadata


class CacheInterceptor(NestInterceptor):
    def __init__(self, cache: CacheService):
        self.cache = cache

    def track_by(self, context: ExecutionContext) -> str | None:
        """The cache key for this request, or ``None`` to skip caching it."""
        explicit = get_metadata(CACHE_KEY_METADATA, context.get_handler())
        if explicit:
            return str(explicit)
        request: Request = context.get_request()
        if request.method != "GET":
            return None
        query = "&".join(f"{k}={v}" for k, v in sorted(request.query_params.multi_items()))
        return f"{request.url.path}?{query}" if query else request.url.path

    async def intercept(self, context: ExecutionContext, next: CallHandler) -> Any:
        key = self.track_by(context)
        if key is None:
            return await next.handle()
        cached = await self.cache.get(key)
        if cached is not None:
            return cached
        result = await next.handle()
        if result is not None and not isinstance(result, Response | StreamableFile):
            ttl = get_metadata(CACHE_TTL_METADATA, context.get_handler())
            await self.cache.set(key, result, ttl)
        return result
