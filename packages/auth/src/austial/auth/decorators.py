"""Decorators: ``@Public`` and ``CurrentUser``.

``@Public`` marks a route as unauthenticated -- ``AuthGuard`` checks for this
metadata and short-circuits.

``CurrentUser`` binds the authenticated principal (``request.state.user``, set by
``AuthGuard``) into a handler parameter, resolved *after* every guard for the route has
run -- unlike a plain FastAPI ``Depends``, which would resolve before the guard loop and
always see an empty ``request.state`` (see ``austial.common.FromRequestState``). If no
guard ran (e.g. the route is ``@Public``) the value is ``None``, so handlers can accept
an optional user cleanly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from austial.common.decorators.params import FromRequestState
from austial.core.metadata import get_metadata, set_metadata

IS_PUBLIC_METADATA = "austial:auth:is_public"


def Public() -> Callable:  # noqa: N802 - decorator naming mirrors Nest's ``@Public()``
    """Mark a controller class or a single route handler as public. ``AuthGuard``
    treats a decorated target as unauthenticated and allows the request through."""

    def decorator(target):
        set_metadata(IS_PUBLIC_METADATA, True)(target)
        return target

    return decorator


def is_public(target: Any) -> bool:
    """Return ``True`` if ``target`` (a handler or its owning class) is marked public."""
    return bool(get_metadata(IS_PUBLIC_METADATA, target, False))


def CurrentUser() -> Any:  # noqa: N802 - Nest-parity naming
    """Inject the authenticated principal (set by ``AuthGuard``) into a handler
    parameter. Returns ``None`` on a ``@Public`` route.

    Usage::

        @Controller("/me")
        class MeController:
            @Get()
            def me(self, user=CurrentUser()):
                return {"id": user.subject}
    """
    return FromRequestState("user", default=None)
