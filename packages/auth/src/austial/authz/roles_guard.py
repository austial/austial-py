"""``RolesGuard`` -- checks ``@Roles``, ``@Permissions``, then ``@AuthorizeObject``.

Order matters: cheap claim checks first, expensive object-level rule last.
Reads the authenticated principal from ``request.state.user`` (set by
``AuthGuard``). No principal + no metadata => allow (the route is public
w.r.t. authz) unless ``deny_undeclared`` is set. No principal + metadata => 403.
"""

from __future__ import annotations

from typing import Any

from austial.authz.decorators import (
    AUTHORIZE_OBJECT_METADATA,
    PERMISSIONS_METADATA,
    ROLES_METADATA,
)
from austial.authz.errors import InsufficientPermissionsError, InsufficientRolesError
from austial.authz.permission_service import PermissionService
from austial.common.decorators.injectable import Injectable
from austial.common.exceptions import ForbiddenException
from austial.common.guards.base import CanActivate, ExecutionContext
from austial.core.metadata import get_metadata


def _merge(handler_meta: tuple[Any, ...], class_meta: tuple[Any, ...]) -> tuple[Any, ...]:
    """Union of class-level and handler-level metadata (both apply)."""
    return tuple(dict.fromkeys(class_meta + handler_meta))


@Injectable()
class RolesGuard(CanActivate):
    #: Deny-by-default. ``False`` (the default) lets a handler that declares no ``@Roles``,
    #: ``@Permissions`` or ``@AuthorizeObject`` through, so a forgotten decorator is silently open to
    #: every authenticated caller. A product that wants "every route must declare a policy" subclasses
    #: and sets ``True``: an undeclared handler is then a 403 (the subclass lets ``@Public`` routes
    #: through first).
    deny_undeclared: bool = False

    async def can_activate(self, context: ExecutionContext) -> bool:
        handler = context.get_handler()
        controller = context.get_class()

        required_roles = _merge(
            tuple(get_metadata(ROLES_METADATA, handler, ())),
            tuple(get_metadata(ROLES_METADATA, controller, ())),
        )
        required_perms = _merge(
            tuple(get_metadata(PERMISSIONS_METADATA, handler, ())),
            tuple(get_metadata(PERMISSIONS_METADATA, controller, ())),
        )
        object_rule = get_metadata(AUTHORIZE_OBJECT_METADATA, handler, None) or get_metadata(
            AUTHORIZE_OBJECT_METADATA, controller, None
        )

        if not required_roles and not required_perms and object_rule is None:
            if self.deny_undeclared:
                raise ForbiddenException("No access policy declared for this route")
            return True

        request = context.get_request()
        principal = getattr(request.state, "user", None)
        if principal is None:
            # metadata requires something, no principal => fail closed
            raise ForbiddenException("Authentication required")

        if required_roles and not PermissionService.has_any_role(principal, required_roles):
            raise InsufficientRolesError(required_roles, PermissionService.get_roles(principal))

        if required_perms and not PermissionService.has_all_permissions(principal, required_perms):
            raise InsufficientPermissionsError(required_perms, PermissionService.get_permissions(principal))

        if object_rule is not None:
            ok = object_rule(principal, request)
            if not ok:
                raise ForbiddenException("Object authorisation denied")

        return True
