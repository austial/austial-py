"""Per-request context for ``Scope.REQUEST`` providers -- mirrors Nest's ``ContextId`` /
``ContextIdFactory`` and the injectable ``REQUEST`` token.

A request-scoped provider is built once per *context* (normally one HTTP request) and cached
in that context's own ``cache`` dict. Python has no per-request DI tree like Nest, so the
active context is carried in a :mod:`contextvars` variable, which follows ``await`` chains and
``asyncio`` tasks exactly the way a request does.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

# Injection token: `Inject(REQUEST)` resolves to the current Starlette ``Request``. Any
# provider that depends on it (directly or transitively) becomes request-scoped implicitly.
REQUEST = "REQUEST"

_REQUEST_STATE_ATTR = "__austial_context_id__"


class ContextId:
    """One request-scoped provider cache. Mirrors Nest's ``ContextId``."""

    __slots__ = ("cache", "request")

    def __init__(self, request: Any = None) -> None:
        self.cache: dict[Any, Any] = {}
        self.request = request

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ContextId(providers={len(self.cache)})"


class ContextIdFactory:
    @staticmethod
    def create() -> ContextId:
        """A fresh, empty context -- e.g. for a queue worker or a manual
        ``ModuleRef.resolve(Token, context_id)`` outside any HTTP request."""
        return ContextId()

    @staticmethod
    def get_by_request(request: Any) -> ContextId:
        """The context bound to ``request``, created on first use, so every call for the
        same request returns the same ``ContextId`` (same cache, same provider instances)."""
        state = request.state
        context_id = getattr(state, _REQUEST_STATE_ATTR, None)
        if context_id is None:
            context_id = ContextId(request)
            setattr(state, _REQUEST_STATE_ATTR, context_id)
        return context_id


_current_context: ContextVar[ContextId | None] = ContextVar("austial_context_id", default=None)


def get_current_context() -> ContextId | None:
    return _current_context.get()


class use_context:  # noqa: N801 - context-manager, lower-case reads better at call sites
    """``with use_context(ctx):`` -- makes ``ctx`` the active context for DI resolution."""

    def __init__(self, context_id: ContextId) -> None:
        self._context_id = context_id
        self._token: Any = None

    def __enter__(self) -> ContextId:
        self._token = _current_context.set(self._context_id)
        return self._context_id

    def __exit__(self, *exc_info: Any) -> None:
        _current_context.reset(self._token)
