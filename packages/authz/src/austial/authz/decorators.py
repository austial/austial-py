"""``@Roles(...)``, ``@Permissions(...)``, ``@AuthorizeObject(rule)`` -- metadata
decorators the ``RolesGuard`` reads.

Semantics:

- ``@Roles(*names)`` -- caller must hold **any** of the listed roles.
- ``@Permissions(*names)`` -- caller must hold **all** of the listed permissions.
- ``@AuthorizeObject(rule)`` -- takes a callable ``(principal, request) -> bool``.
  Runs after roles/permissions succeed, so it is the object-level gate.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from austial.core.metadata import get_metadata, set_metadata

ROLES_METADATA = "austial:authz:roles"
PERMISSIONS_METADATA = "austial:authz:permissions"
AUTHORIZE_OBJECT_METADATA = "austial:authz:authorize_object"


def Roles(*roles: str) -> Callable:  # noqa: N802
    """Require the principal to hold ANY of the given roles."""

    def decorator(target):
        existing = tuple(get_metadata(ROLES_METADATA, target, ()))
        set_metadata(ROLES_METADATA, existing + tuple(roles))(target)
        return target

    return decorator


def Permissions(*permissions: str) -> Callable:  # noqa: N802
    """Require the principal to hold ALL of the given permissions."""

    def decorator(target):
        existing = tuple(get_metadata(PERMISSIONS_METADATA, target, ()))
        set_metadata(PERMISSIONS_METADATA, existing + tuple(permissions))(target)
        return target

    return decorator


def AuthorizeObject(rule: Callable[[Any, Any], bool]) -> Callable:  # noqa: N802
    """Attach an object-level authorisation callable to a handler.

    ``rule(principal, request) -> bool`` runs after role/permission checks pass.
    Returning ``False`` (or raising) rejects the request."""

    def decorator(target):
        set_metadata(AUTHORIZE_OBJECT_METADATA, rule)(target)
        return target

    return decorator
