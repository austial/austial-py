"""``CacheService`` -- mirrors Nest's ``CACHE_MANAGER``: ``get`` / ``set`` / ``delete`` / ``clear``
plus ``wrap`` (compute-on-miss, with concurrent callers sharing one computation)."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from austial.cache.store import CacheStore, MemoryCacheStore
from austial.common.decorators.injectable import Inject


@dataclass
class CacheOptions:
    ttl: float | None = 5.0  # default time-to-live, seconds; None = never expires
    max_items: int = 1000  # MemoryCacheStore size
    store: CacheStore | None = None  # supply your own backend


CACHE_OPTIONS = "AUSTIAL_CACHE_OPTIONS"


class CacheService:
    def __init__(self, options: CacheOptions = Inject(CACHE_OPTIONS)):
        self.options = options or CacheOptions()
        # `is not None`, not truthiness: an empty MemoryCacheStore has len() == 0 and is falsy.
        store = self.options.store
        self.store: CacheStore = store if store is not None else MemoryCacheStore(max_items=self.options.max_items)
        self._inflight: dict[str, asyncio.Future[Any]] = {}

    @property
    def default_ttl(self) -> float | None:
        return self.options.ttl

    async def get(self, key: str) -> Any:
        return await self.store.get(key)

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Stores ``value``. ``ttl`` (seconds) overrides the default; pass ``0`` for no expiry."""
        await self.store.set(key, value, self.default_ttl if ttl is None else ttl)

    async def delete(self, key: str) -> None:
        await self.store.delete(key)

    async def clear(self) -> None:
        await self.store.clear()

    async def wrap(self, key: str, factory: Callable[[], Any | Awaitable[Any]], ttl: float | None = None) -> Any:
        """Returns the cached value for ``key``, computing and storing it with ``factory`` on a miss.
        Concurrent misses for the same key share one ``factory`` call (no cache stampede)."""
        cached = await self.store.get(key)
        if cached is not None:
            return cached
        pending = self._inflight.get(key)
        if pending is not None:
            return await pending
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            result = factory()
            if inspect.isawaitable(result):
                result = await result
            await self.set(key, result, ttl)
            future.set_result(result)
            return result
        except BaseException as exc:
            future.set_exception(exc)
            future.exception()  # mark retrieved, so an un-awaited failure doesn't log "never retrieved"
            raise
        finally:
            self._inflight.pop(key, None)
