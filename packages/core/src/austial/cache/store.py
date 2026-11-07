"""Cache stores. ``MemoryCacheStore`` is the default; implement ``CacheStore`` to back the cache
with Redis, Memcached or anything else (see the docs for a Redis sketch)."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

_MISSING = object()


class CacheStore(ABC):
    """The storage backend. ``ttl`` is in **seconds** (``None`` = no expiry). ``get`` returns
    ``None`` for a miss, so a stored ``None`` is indistinguishable from absence -- store a sentinel
    if you need to cache "no result"."""

    @abstractmethod
    async def get(self, key: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def clear(self) -> None:
        raise NotImplementedError


class MemoryCacheStore(CacheStore):
    """In-process store: entries expire after their TTL and, past ``max_items``, the least recently
    used one is evicted. Not shared between processes -- use a networked store for that."""

    def __init__(self, *, max_items: int = 1000, clock: Callable[[], float] = time.monotonic) -> None:
        if max_items < 1:
            raise ValueError("max_items must be at least 1")
        self._max_items = max_items
        self._clock = clock
        self._data: OrderedDict[str, tuple[Any, float | None]] = OrderedDict()

    def __len__(self) -> int:
        return len(self._data)

    def _live(self, key: str) -> Any:
        entry = self._data.get(key)
        if entry is None:
            return _MISSING
        value, expires_at = entry
        if expires_at is not None and self._clock() >= expires_at:
            del self._data[key]
            return _MISSING
        self._data.move_to_end(key)
        return value

    async def get(self, key: str) -> Any:
        value = self._live(key)
        return None if value is _MISSING else value

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        expires_at = None if ttl is None or ttl <= 0 else self._clock() + ttl
        self._data[key] = (value, expires_at)
        self._data.move_to_end(key)
        while len(self._data) > self._max_items:
            self._data.popitem(last=False)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def clear(self) -> None:
        self._data.clear()
