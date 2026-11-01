"""``LocaleMiddleware`` -- populates ``I18nContext`` from the incoming request.

Precedence, highest to lowest:

1. A fallback header (default: ``X-Locale``). Product code sets this from an
   authenticated user's stored preference before the request reaches the app.
2. The ``Accept-Language`` header, parsed with ``q``-weighting. The first tag
   that has translations loaded wins; if no tag matches, the language subtag
   is tried (``en-IN`` -> ``en``) so a browser sending ``en-IN`` still gets
   English when only ``en`` is deployed.
3. The configured default locale.

The resolved locale is written into ``I18nContext`` for the duration of the
request. The reset is a no-op on the framework's request lifecycle -- the
contextvar is task-local and released when the task ends -- but is provided
for hosts that reuse a single task for multiple requests.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import Response

from austial.common.middleware.base import NestMiddleware
from austial.i18n.config import I18nConfig
from austial.i18n.i18n_context import I18nContext
from austial.i18n.i18n_service import I18nService


@dataclass(frozen=True, slots=True)
class _WeightedTag:
    tag: str
    q: float


def parse_accept_language(header: str) -> list[str]:
    """Return the ``Accept-Language`` tags in descending ``q``-order.

    A malformed piece is skipped rather than failing the whole request.
    """
    if not header:
        return []
    entries: list[_WeightedTag] = []
    for raw in header.split(","):
        piece = raw.strip()
        if not piece:
            continue
        tag, _, params = piece.partition(";")
        tag = tag.strip()
        if not tag or tag == "*":
            continue
        q = 1.0
        for param in params.split(";"):
            param = param.strip()
            if param.startswith("q="):
                try:
                    q = float(param[2:])
                except ValueError:
                    q = 0.0
        entries.append(_WeightedTag(tag=tag, q=q))
    # Stable sort: preserve source order among equal q values.
    entries.sort(key=lambda e: e.q, reverse=True)
    return [e.tag for e in entries if e.q > 0]


class LocaleMiddleware(NestMiddleware):
    """Parses locale from the request and pushes it into ``I18nContext``.

    Constructed by ``I18nModule.for_root``; injected with the service so it
    can consult ``available_locales()`` to pick the best match rather than
    blindly trusting the header.
    """

    def __init__(self, service: I18nService, config: I18nConfig, *, locale_header: str = "X-Locale"):
        self._service = service
        self._config = config
        self._locale_header = locale_header

    async def use(self, request: Request, call_next: Callable[[], Awaitable[Response]]) -> Response:
        resolved = self._resolve(request)
        token = I18nContext.set(resolved)
        try:
            return await call_next()
        finally:
            I18nContext.reset(token)

    # ------------------------------------------------------------------

    def _resolve(self, request: Request) -> str:
        available = set(self._service.available_locales())

        override = request.headers.get(self._locale_header)
        if override:
            picked = self._match(override, available)
            if picked:
                return picked

        accept = request.headers.get("Accept-Language", "")
        for tag in parse_accept_language(accept):
            picked = self._match(tag, available)
            if picked:
                return picked

        return self._config.default_locale

    def _match(self, tag: str, available: set[str]) -> str | None:
        """Match ``tag`` against loaded locales.

        Tries the exact tag first, then the language-only subtag
        (``en-IN`` -> ``en``), then any loaded locale that starts with
        the language subtag (``pt`` -> ``pt-BR``).
        """
        if tag in available:
            return tag
        primary = tag.split("-", 1)[0]
        if primary and primary in available:
            return primary
        for candidate in sorted(available):
            if candidate.split("-", 1)[0] == primary:
                return candidate
        return None
