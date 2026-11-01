"""``TenancyModule.for_root(...)`` -- provides ``TenantContext`` and ``TenantGuard``."""

from __future__ import annotations

from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule
from austial.tenancy.tenant_context import TenantContext
from austial.tenancy.tenant_guard import TenantGuard


@Module()
class TenancyModule:
    @staticmethod
    def for_root(*, is_global: bool = True) -> DynamicModule:
        return DynamicModule(
            module=TenancyModule,
            providers=[TenantContext, TenantGuard],
            exports=[TenantContext, TenantGuard],
        )
