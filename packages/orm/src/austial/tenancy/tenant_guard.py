"""``TenantGuard`` -- extracts tenant from the authenticated principal and
populates ``TenantContext``.

Runs after ``AuthGuard`` (which sets ``request.state.user``). Reads the
``tenant`` claim from the principal, populates the context, and stores a
reset token on ``request.state`` so the framework can tear the context down
at end-of-request.

On success the tenant id is published both on ``TenantContext`` (contextvar) and on
``request.state.tenant`` (read by ``austial.audit`` so audit rows carry the tenant).

Fails closed:

- If the handler/controller carries ``@RequireTenant`` and the principal has
  no ``tenant`` claim, raises ``MissingTenantError`` (403).
- If the URL/body contains a ``tenant_id`` that disagrees with the claim,
  raises ``TenantMismatchError`` (403). Product code opts in by overriding
  ``read_body_tenant`` -- the base guard does not scan bodies to keep the
  hot path fast.
"""

from __future__ import annotations

from typing import Any

from austial.common.decorators.injectable import Injectable
from austial.common.guards.base import CanActivate, ExecutionContext
from austial.tenancy.decorators import is_tenant_required
from austial.tenancy.errors import MissingTenantError, TenantMismatchError
from austial.tenancy.tenant_context import TenantContext, TenantContextValue


@Injectable()
class TenantGuard(CanActivate):
    #: Treat every route as ``@RequireTenant`` (deny-by-default). Subclass and set ``True`` for a product
    #: whose every non-public route is tenant-scoped, so a forgotten decorator cannot ship an endpoint
    #: that runs without a tenant. The subclass is responsible for letting public routes through
    #: *before* delegating here.
    require_by_default: bool = False

    async def can_activate(self, context: ExecutionContext) -> bool:
        handler = context.get_handler()
        controller = context.get_class()
        required = self.require_by_default or is_tenant_required(handler) or is_tenant_required(controller)

        request = context.get_request()
        principal = getattr(request.state, "user", None)
        claim = None
        if principal is not None:
            claim = principal.claims.get("tenant") if isinstance(principal.claims, dict) else None

        if not claim:
            if required:
                raise MissingTenantError()
            return True

        path_tenant = request.path_params.get("tenant_id") if hasattr(request, "path_params") else None
        if path_tenant is not None and str(path_tenant) != str(claim):
            raise TenantMismatchError(str(claim), str(path_tenant))

        token = TenantContext.set(TenantContextValue(tenant_id=str(claim)))
        request.state.tenant_reset_token = token
        # ``AuditedInterceptor`` reads the tenant from ``request.state.tenant``.
        request.state.tenant = str(claim)
        return True

    def teardown(self, request: Any) -> None:
        """Reset the contextvar after the response is sent. The framework's
        request lifecycle should call this from a teardown hook; if it doesn't,
        the contextvar is still request-scoped in async contexts and gets
        released with the task."""
        token = getattr(request.state, "tenant_reset_token", None)
        if token is not None:
            TenantContext.reset(token)
