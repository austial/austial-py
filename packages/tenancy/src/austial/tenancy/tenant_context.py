"""``TenantContext`` -- request-scoped tenant id.

Backed by ``contextvars.ContextVar`` so the value is isolated per request even
across ``await`` points and threadpool executors. Set by ``TenantGuard`` at the
perimeter; read by services, repositories and the ``@RequireTenant`` decorator.

Two access styles are supported:

- Injectable: ``TenantContext`` is a provider; inject and call ``current_id()``.
- Direct: ``TenantContext.get()`` is a classmethod for places DI is inconvenient
  (a mixin, a pure function, a background job that has been handed a snapshot).
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any

from austial.common.decorators.injectable import Injectable

_current_tenant: contextvars.ContextVar[TenantContextValue | None] = contextvars.ContextVar(
    "austial.tenancy.tenant", default=None
)


@dataclass(frozen=True, slots=True)
class TenantContextValue:
    """Snapshot of the current tenant. ``metadata`` carries whatever the
    ``TenantGuard`` chose to expose (e.g. tenant name, plan) for downstream code."""

    tenant_id: str
    metadata: dict[str, Any] | None = None


@Injectable()
class TenantContext:
    """Injectable facade over the contextvar."""

    @classmethod
    def get(cls) -> TenantContextValue | None:
        """Return the current value, or ``None`` if unset."""
        return _current_tenant.get()

    @classmethod
    def require(cls) -> TenantContextValue:
        """Return the current value, or raise ``MissingTenantError`` if unset."""
        from austial.tenancy.errors import MissingTenantError

        value = _current_tenant.get()
        if value is None:
            raise MissingTenantError()
        return value

    @classmethod
    def set(cls, value: TenantContextValue | None) -> contextvars.Token:
        """Set the current value; return a token the caller can use to reset."""
        return _current_tenant.set(value)

    @classmethod
    def reset(cls, token: contextvars.Token) -> None:
        _current_tenant.reset(token)

    def current(self) -> TenantContextValue | None:
        """Instance form for injected use."""
        return _current_tenant.get()

    def current_id(self) -> str:
        """Instance form; raises ``MissingTenantError`` if unset."""
        return self.__class__.require().tenant_id
