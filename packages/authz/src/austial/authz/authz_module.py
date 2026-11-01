"""``AuthzModule.for_root(...)`` -- provides ``RolesGuard`` and ``PermissionService``."""

from __future__ import annotations

from austial.authz.permission_service import PermissionService
from austial.authz.roles_guard import RolesGuard
from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule


@Module()
class AuthzModule:
    @staticmethod
    def for_root(*, is_global: bool = True) -> DynamicModule:
        return DynamicModule(
            module=AuthzModule,
            providers=[RolesGuard, PermissionService],
            exports=[RolesGuard, PermissionService],
        )
