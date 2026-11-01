"""``SecureHeadersMiddleware`` -- sets baseline security response headers.

Applied module-wide via ``consumer.apply(SecureHeadersMiddleware).for_routes("*")``.
Reads its policy from ``SecurityConfig``; product code overrides the CSP string
(or any other header) by passing a customised config to ``SecurityModule.for_root``.

Headers set on every response:

- ``Content-Security-Policy`` -- from ``config.csp``.
- ``Strict-Transport-Security`` -- ``max-age=<hsts_max_age>; includeSubDomains``.
- ``X-Content-Type-Options: nosniff``.
- ``Referrer-Policy: strict-origin-when-cross-origin``.
- ``X-Frame-Options: DENY``.
- ``Permissions-Policy`` -- from ``config.permissions_policy``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

from austial.common.middleware.base import NestMiddleware
from austial.security.config import SecurityConfig


class SecureHeadersMiddleware(NestMiddleware):
    """Constructor takes a ``SecurityConfig`` (supplied by the DI container).

    Middleware is instantiated per binding; the config is snapshotted at
    startup so the header set is stable for the process lifetime."""

    def __init__(self, config: SecurityConfig | None = None) -> None:
        self._config = config or SecurityConfig()

    async def use(self, request: Request, call_next: Callable[[], Awaitable[Response]]) -> Response:
        response = await call_next()
        headers = response.headers
        headers.setdefault("Content-Security-Policy", self._config.csp)
        headers.setdefault(
            "Strict-Transport-Security",
            f"max-age={self._config.hsts_max_age}; includeSubDomains",
        )
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Permissions-Policy", self._config.permissions_policy)
        return response
