"""``austial.tenancy`` -- multi-tenant primitives.

Provides ``TenantContext`` (request-scoped, backed by ``contextvars`` so it works with
async and thread executors), ``TenantGuard`` (populates the context from the
authenticated JWT's ``tenant`` claim and fails-closed on absence), the ``@Tenanted``
entity mixin (adds a ``tenant_id`` column), and ``@RequireTenant`` (marker decorator
that requires ``TenantGuard`` to have populated the context before the handler runs).

The framework enforces the tenant boundary at the request perimeter; product code
still writes ``.where(tenant_id=current)`` in queries or uses a scoped repository, so
the tenant filter is explicit at the persistence boundary (visible in every query
plan review) rather than magically injected.
"""

from austial.tenancy.decorators import REQUIRE_TENANT_METADATA, RequireTenant, is_tenant_required
from austial.tenancy.errors import MissingTenantError, TenantMismatchError
from austial.tenancy.tenancy_module import TenancyModule
from austial.tenancy.tenant_context import TenantContext, TenantContextValue
from austial.tenancy.tenant_guard import TenantGuard
from austial.tenancy.tenanted import Tenanted

__all__ = [
    "MissingTenantError",
    "REQUIRE_TENANT_METADATA",
    "RequireTenant",
    "TenancyModule",
    "Tenanted",
    "TenantContext",
    "TenantContextValue",
    "TenantGuard",
    "TenantMismatchError",
    "is_tenant_required",
]
