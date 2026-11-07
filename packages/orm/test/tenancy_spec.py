"""``austial.tenancy`` unit tests.

Exercises the four load-bearing behaviours:

- ``TenantContext`` is request-scoped: setting it in one task does not leak into
  another; a reset restores the prior value.
- ``TenantContext.require()`` raises when unset.
- ``TenantGuard`` populates the context from the ``tenant`` claim of the
  authenticated principal.
- ``TenantGuard`` fails-closed on ``@RequireTenant`` handlers with no claim,
  and fails-closed on a path-tenant that disagrees with the claim.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from austial.common import ExecutionContext
from austial.tenancy import (
    MissingTenantError,
    RequireTenant,
    TenantContext,
    TenantContextValue,
    TenantGuard,
    TenantMismatchError,
)


class _FakeExecutionContext(ExecutionContext):
    def __init__(self, request, controller_class, handler):
        self._request = request
        self._controller_class = controller_class
        self._handler = handler

    def get_request(self):
        return self._request

    def get_class(self):
        return self._controller_class

    def get_handler(self):
        return self._handler


def _principal(tenant: str | None):
    return SimpleNamespace(claims={"tenant": tenant} if tenant is not None else {})


def _request(principal, path_params: dict | None = None):
    return SimpleNamespace(
        state=SimpleNamespace(user=principal),
        path_params=path_params or {},
    )


# ---------------------------------------------------------------------------
# TenantContext


def test_context_starts_unset():
    assert TenantContext.get() is None


def test_context_require_raises_when_unset():
    with pytest.raises(MissingTenantError):
        TenantContext.require()


def test_context_set_and_reset_round_trip():
    token = TenantContext.set(TenantContextValue(tenant_id="acme"))
    try:
        assert TenantContext.require().tenant_id == "acme"
    finally:
        TenantContext.reset(token)
    assert TenantContext.get() is None


@pytest.mark.asyncio
async def test_context_is_request_scoped_across_tasks():
    # Two concurrent tasks set different tenants; neither should see the other's.
    async def task(tenant: str):
        token = TenantContext.set(TenantContextValue(tenant_id=tenant))
        try:
            await asyncio.sleep(0)  # yield to the scheduler
            return TenantContext.require().tenant_id
        finally:
            TenantContext.reset(token)

    seen = await asyncio.gather(task("acme"), task("initech"), task("hooli"))
    assert sorted(seen) == ["acme", "hooli", "initech"]
    # After all tasks complete, the outer context is still unset
    assert TenantContext.get() is None


# ---------------------------------------------------------------------------
# TenantGuard


@pytest.mark.asyncio
async def test_guard_populates_context_from_claim():
    guard = TenantGuard()

    def handler():
        pass

    req = _request(_principal("acme"))
    ctx = _FakeExecutionContext(req, object, handler)
    assert await guard.can_activate(ctx) is True
    assert TenantContext.require().tenant_id == "acme"
    guard.teardown(req)


@pytest.mark.asyncio
async def test_guard_is_permissive_without_require_marker():
    guard = TenantGuard()

    def handler():
        pass

    # No principal at all: guard allows through so a @Public route can still run
    req = _request(None)
    ctx = _FakeExecutionContext(req, object, handler)
    assert await guard.can_activate(ctx) is True
    assert TenantContext.get() is None


@pytest.mark.asyncio
async def test_guard_rejects_missing_tenant_when_required():
    guard = TenantGuard()

    @RequireTenant()
    def handler():
        pass

    req = _request(_principal(None))
    ctx = _FakeExecutionContext(req, object, handler)
    with pytest.raises(MissingTenantError):
        await guard.can_activate(ctx)


@pytest.mark.asyncio
async def test_guard_rejects_tenant_path_mismatch():
    guard = TenantGuard()

    def handler():
        pass

    req = _request(_principal("acme"), path_params={"tenant_id": "hooli"})
    ctx = _FakeExecutionContext(req, object, handler)
    with pytest.raises(TenantMismatchError):
        await guard.can_activate(ctx)


@pytest.mark.asyncio
async def test_guard_publishes_tenant_on_request_state_for_the_audit_interceptor():
    guard = TenantGuard()

    def handler():
        pass

    req = _request(_principal("acme"))
    assert await guard.can_activate(_FakeExecutionContext(req, object, handler)) is True
    assert req.state.tenant == "acme"
    guard.teardown(req)


@pytest.mark.asyncio
async def test_require_by_default_subclass_rejects_undecorated_handler_without_tenant():
    class StrictTenantGuard(TenantGuard):
        require_by_default = True

    def handler():
        pass

    with pytest.raises(MissingTenantError):
        await StrictTenantGuard().can_activate(_FakeExecutionContext(_request(_principal(None)), object, handler))


def test_tenanted_mixin_adds_a_required_indexed_tenant_id_column():
    from austial.orm import Entity, PrimaryColumn
    from austial.orm.decorators.entity import get_entity_metadata
    from austial.orm.metadata.column_types import String
    from austial.tenancy import Tenanted

    @Entity("tenanted_widgets")
    class Widget(Tenanted):
        id: str = PrimaryColumn(type_=String(length=36))

    column = get_entity_metadata(Widget).column("tenant_id")
    assert column is not None and column.index is True and column.nullable is False
    # mypy caveat (documented in content/techniques/multi-tenancy.mdx#tenanted-entities): `Tenanted`
    # is a plain mixin, not itself part of the dataclass_transform chain, so mypy doesn't see
    # `tenant_id` as a constructor parameter even though it works correctly at runtime.
    assert Widget(id="w1", tenant_id="acme").tenant_id == "acme"  # type: ignore[call-arg]
