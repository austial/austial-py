"""``austial.cache`` -- caching, mirrors ``@nestjs/cache-manager``.

from austial.cache import CacheModule, CacheService, CacheInterceptor, CacheKey, CacheTTL
"""

from austial.cache.cache_interceptor import CacheInterceptor
from austial.cache.cache_module import CacheModule
from austial.cache.cache_service import CACHE_OPTIONS, CacheOptions, CacheService
from austial.cache.decorators import CacheKey, CacheTTL
from austial.cache.store import CacheStore, MemoryCacheStore

__all__ = [
    "CACHE_OPTIONS",
    "CacheInterceptor",
    "CacheKey",
    "CacheModule",
    "CacheOptions",
    "CacheService",
    "CacheStore",
    "CacheTTL",
    "MemoryCacheStore",
]
