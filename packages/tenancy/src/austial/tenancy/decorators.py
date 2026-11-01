"""``@RequireTenant`` -- marker decorator that ``TenantGuard`` checks.

Apply at controller or handler level to require a populated ``TenantContext``.
Requests without a tenant claim (or with a claim that fails product-level
validation) are rejected with 403 before the handler runs.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from austial.core.metadata import get_metadata, set_metadata

REQUIRE_TENANT_METADATA = "austial:tenancy:require"


def RequireTenant() -> Callable:  # noqa: N802 - decorator naming
    """Mark a controller or handler as requiring a tenant context."""

    def decorator(target):
        set_metadata(REQUIRE_TENANT_METADATA, True)(target)
        return target

    return decorator


def is_tenant_required(target: Any) -> bool:
    return bool(get_metadata(REQUIRE_TENANT_METADATA, target, False))
