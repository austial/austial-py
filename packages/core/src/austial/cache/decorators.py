"""``@CacheKey`` and ``@CacheTTL`` -- mirror Nest's decorators of the same name."""

from __future__ import annotations

from collections.abc import Callable

from austial.core.metadata import set_metadata

CACHE_KEY_METADATA = "austial:cache_key"
CACHE_TTL_METADATA = "austial:cache_ttl"


def CacheKey(key: str) -> Callable:  # noqa: N802
    """Cache this route under a fixed ``key`` instead of its URL (so it can be invalidated by name)."""
    return set_metadata(CACHE_KEY_METADATA, key)


def CacheTTL(seconds: float) -> Callable:  # noqa: N802
    """Cache this route for ``seconds`` instead of the module's default."""
    return set_metadata(CACHE_TTL_METADATA, seconds)
