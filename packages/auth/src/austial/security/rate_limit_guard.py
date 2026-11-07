"""``RateLimitGuard`` -- fixed-window rate limiter keyed on ``(client_ip, route)``.

Reads the per-route budget from ``@RateLimit(limit, period_seconds)`` metadata
if present, otherwise falls back to ``SecurityConfig.default_rate_limit``. On a
breach raises ``RateLimitExceededError`` (HTTP 429) carrying a ``Retry-After``
hint that the framework's exception filter can surface on the response.

The default key is ``f"{client_ip}:{method}:{route}"``. Override
``build_key(request)`` in a subclass to use a session id, api key, or tenant id
where those are stronger identifiers. The client IP honours ``X-Forwarded-For`` only
when ``SecurityConfig.trusted_proxy_hops`` says how many proxies you operate.
"""

from __future__ import annotations

from typing import Any

from austial.common.decorators.injectable import Injectable
from austial.common.guards.base import CanActivate, ExecutionContext
from austial.security.config import SecurityConfig
from austial.security.decorators import get_rate_limit
from austial.security.errors import RateLimitExceededError
from austial.security.rate_limit_store import RateLimitStore


@Injectable()
class RateLimitGuard(CanActivate):
    def __init__(self, store: RateLimitStore, config: SecurityConfig) -> None:
        self._store = store
        self._config = config

    async def can_activate(self, context: ExecutionContext) -> bool:
        handler = context.get_handler()
        controller = context.get_class()

        # handler-level metadata wins over class-level, both win over the default
        limit, period = get_rate_limit(handler, get_rate_limit(controller, self._config.default_rate_limit))
        request = context.get_request()
        key = self.build_key(request)

        count, reset_at = self._store.hit(key, period)
        if count > limit:
            import time

            retry_after = max(1, reset_at - int(time.time()))
            raise RateLimitExceededError(
                f"Rate limit exceeded: {limit} requests per {period}s",
                retry_after=retry_after,
            )
        return True

    def build_key(self, request: Any) -> str:
        """Return the counter key for ``request``. Override to key on session,
        api key or tenant. Default is ``f"{client_ip}:{method}:{path}"``, where the client IP is the
        socket peer, or (behind ``SecurityConfig.trusted_proxy_hops`` proxies) the trusted
        ``X-Forwarded-For`` entry."""
        client_ip = self._client_ip(request)
        method = getattr(request, "method", "GET")
        path = getattr(getattr(request, "url", None), "path", "") or getattr(request, "path", "/")
        return f"{client_ip}:{method}:{path}"

    def _client_ip(self, request: Any) -> str:
        hops = self._config.trusted_proxy_hops
        if hops > 0:
            headers = getattr(request, "headers", {}) or {}
            forwarded = None
            try:
                forwarded = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
            except AttributeError:  # pragma: no cover - dict-like headers
                forwarded = None
            if forwarded:
                entries = [e.strip() for e in forwarded.split(",") if e.strip()]
                # The n-th from the right is the address our outermost trusted proxy saw. If the chain is
                # shorter than the configured hop count the header is not from our proxy: ignore it.
                if len(entries) >= hops:
                    return entries[-hops]
        client = getattr(request, "client", None)
        if client is not None:
            host = getattr(client, "host", None)
            if host:
                return host
        return "unknown"
