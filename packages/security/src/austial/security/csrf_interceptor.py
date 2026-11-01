"""``CsrfInterceptor`` -- double-submit cookie CSRF check for cookie-authenticated
flows.

The pattern:

- The server sets a random token in the ``csrf_token`` cookie at session start.
- Every state-changing request must echo the same token back in the
  ``X-CSRF-Token`` header.
- The interceptor compares the two values in constant time and rejects on any
  mismatch.

Bearer-token flows are exempt: an ``Authorization: Bearer ...`` header cannot
be attached cross-origin without the caller possessing the credential outright,
which defeats the CSRF threat model. Read-only methods (``GET``/``HEAD``/
``OPTIONS``) are exempt as well; they should not carry side effects.

Raises ``ForbiddenException`` (HTTP 403) on a mismatch so a proxy or WAF can
distinguish CSRF failures from generic 401s.
"""

from __future__ import annotations

import hmac
from typing import Any

from austial.common.exceptions import ForbiddenException
from austial.common.guards.base import ExecutionContext
from austial.common.interceptors.base import CallHandler, NestInterceptor

CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_COOKIE_NAME = "csrf_token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class CsrfInterceptor(NestInterceptor):
    """Enforce the double-submit cookie invariant before the handler runs.

    Product code sets the cookie itself (usually at login); this interceptor is
    the read-side check."""

    def __init__(
        self,
        *,
        header_name: str = CSRF_HEADER_NAME,
        cookie_name: str = CSRF_COOKIE_NAME,
    ) -> None:
        self._header = header_name
        self._cookie = cookie_name

    async def intercept(self, context: ExecutionContext, next: CallHandler) -> Any:
        request = context.get_request()
        method = getattr(request, "method", "GET").upper()

        if method in _SAFE_METHODS:
            return await next.handle()

        # Bearer-authenticated request => skip CSRF (not the relevant threat model).
        auth = _header(getattr(request, "headers", {}) or {}, "Authorization")
        if auth and auth.lower().startswith("bearer "):
            return await next.handle()

        header_token = _header(getattr(request, "headers", {}) or {}, self._header)
        cookie_token = _cookie(request, self._cookie)

        if not header_token or not cookie_token:
            raise ForbiddenException("CSRF token missing")

        if not hmac.compare_digest(header_token, cookie_token):
            raise ForbiddenException("CSRF token mismatch")

        return await next.handle()


def _header(headers: Any, name: str) -> str | None:
    try:
        value = headers.get(name)
    except AttributeError:
        return None
    if value:
        return value
    try:
        return headers.get(name.lower())
    except AttributeError:
        return None


def _cookie(request: Any, name: str) -> str | None:
    cookies = getattr(request, "cookies", None)
    if cookies is None:
        return None
    try:
        return cookies.get(name)
    except AttributeError:
        return None
