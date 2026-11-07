"""``PermissionService`` -- programmatic role/permission checks.

Use from services or background jobs where a decorator is inconvenient. Also
carries the type alias used by ``@AuthorizeObject``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from austial.common.decorators.injectable import Injectable

# ``(principal, request_or_context) -> bool``. Product code implements the rule.
ObjectAuthorizationRule = Callable[[Any, Any], bool]


@Injectable()
class PermissionService:
    @staticmethod
    def has_any_role(principal: Any, roles: tuple[str, ...]) -> bool:
        """True if ``principal.claims['roles']`` intersects ``roles``. Missing
        claim => False."""
        actual = _actual_roles(principal)
        return any(r in actual for r in roles)

    @staticmethod
    def has_all_permissions(principal: Any, permissions: tuple[str, ...]) -> bool:
        """True if every requested permission is in ``principal.claims['permissions']``."""
        actual = _actual_permissions(principal)
        return all(p in actual for p in permissions)

    @staticmethod
    def get_roles(principal: Any) -> tuple[str, ...]:
        return _actual_roles(principal)

    @staticmethod
    def get_permissions(principal: Any) -> tuple[str, ...]:
        return _actual_permissions(principal)


def _actual_roles(principal: Any) -> tuple[str, ...]:
    if principal is None or not hasattr(principal, "claims"):
        return ()
    claims = principal.claims or {}
    value = claims.get("roles", ()) if isinstance(claims, dict) else ()
    return tuple(value) if isinstance(value, list | tuple) else ()


def _actual_permissions(principal: Any) -> tuple[str, ...]:
    if principal is None or not hasattr(principal, "claims"):
        return ()
    claims = principal.claims or {}
    value = claims.get("permissions", ()) if isinstance(claims, dict) else ()
    return tuple(value) if isinstance(value, list | tuple) else ()
