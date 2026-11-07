"""``austial.authz`` -- role- and permission-based access control.

Provides ``@Roles(*names)`` and ``@Permissions(*names)`` metadata decorators,
``RolesGuard`` (rejects requests whose authenticated principal lacks the required
roles/permissions), ``PermissionService`` (programmatic checks from services and
background jobs), and ``@AuthorizeObject(rule)`` (object-level authorisation --
inject the loaded object into the guard's context so the rule can inspect
ownership, tenant, status, etc. before the handler runs).

The framework enforces "does this principal have the claim?" -- product code
decides "what roles does this user have?" by populating the JWT's ``roles`` and
``permissions`` claims at login time.
"""

from austial.authz.authz_module import AuthzModule
from austial.authz.decorators import (
    AUTHORIZE_OBJECT_METADATA,
    PERMISSIONS_METADATA,
    ROLES_METADATA,
    AuthorizeObject,
    Permissions,
    Roles,
)
from austial.authz.errors import InsufficientPermissionsError, InsufficientRolesError
from austial.authz.permission_service import ObjectAuthorizationRule, PermissionService
from austial.authz.roles_guard import RolesGuard

__all__ = [
    "AUTHORIZE_OBJECT_METADATA",
    "AuthzModule",
    "AuthorizeObject",
    "InsufficientPermissionsError",
    "InsufficientRolesError",
    "ObjectAuthorizationRule",
    "PERMISSIONS_METADATA",
    "PermissionService",
    "Permissions",
    "ROLES_METADATA",
    "Roles",
    "RolesGuard",
]
