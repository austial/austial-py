"""``austial.authz`` unit tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from austial.authz import (
    AuthorizeObject,
    InsufficientPermissionsError,
    InsufficientRolesError,
    Permissions,
    PermissionService,
    Roles,
    RolesGuard,
)
from austial.common import ExecutionContext
from austial.common.exceptions import ForbiddenException


class _FakeCtx(ExecutionContext):
    def __init__(self, request, controller_class, handler):
        self._req, self._cls, self._h = request, controller_class, handler

    def get_request(self):
        return self._req

    def get_class(self):
        return self._cls

    def get_handler(self):
        return self._h


def _principal(roles=(), permissions=()):
    return SimpleNamespace(claims={"roles": list(roles), "permissions": list(permissions)})


def _request(principal):
    return SimpleNamespace(state=SimpleNamespace(user=principal))


# PermissionService ---------------------------------------------------------


def test_has_any_role_true_when_one_matches():
    p = _principal(roles=("ops", "compliance"))
    assert PermissionService.has_any_role(p, ("compliance",)) is True


def test_has_any_role_false_on_disjoint():
    p = _principal(roles=("ops",))
    assert PermissionService.has_any_role(p, ("admin",)) is False


def test_has_all_permissions_requires_every_one():
    p = _principal(permissions=("read:invoice", "write:invoice"))
    assert PermissionService.has_all_permissions(p, ("read:invoice",)) is True
    assert PermissionService.has_all_permissions(p, ("read:invoice", "write:invoice")) is True
    assert PermissionService.has_all_permissions(p, ("read:invoice", "delete:invoice")) is False


def test_has_any_role_false_for_missing_principal():
    assert PermissionService.has_any_role(None, ("ops",)) is False


# RolesGuard ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_guard_allows_when_no_metadata_present():
    guard = RolesGuard()

    def handler():
        pass

    ctx = _FakeCtx(_request(None), object, handler)
    assert await guard.can_activate(ctx) is True


@pytest.mark.asyncio
async def test_guard_rejects_without_principal_when_metadata_present():
    guard = RolesGuard()

    @Roles("ops")
    def handler():
        pass

    ctx = _FakeCtx(_request(None), object, handler)
    with pytest.raises(ForbiddenException):
        await guard.can_activate(ctx)


@pytest.mark.asyncio
async def test_guard_allows_role_match():
    guard = RolesGuard()

    @Roles("ops", "admin")
    def handler():
        pass

    ctx = _FakeCtx(_request(_principal(roles=("ops",))), object, handler)
    assert await guard.can_activate(ctx) is True


@pytest.mark.asyncio
async def test_guard_rejects_role_mismatch():
    guard = RolesGuard()

    @Roles("admin")
    def handler():
        pass

    ctx = _FakeCtx(_request(_principal(roles=("ops",))), object, handler)
    with pytest.raises(InsufficientRolesError):
        await guard.can_activate(ctx)


@pytest.mark.asyncio
async def test_guard_rejects_missing_permission():
    guard = RolesGuard()

    @Permissions("delete:invoice")
    def handler():
        pass

    ctx = _FakeCtx(_request(_principal(permissions=("read:invoice",))), object, handler)
    with pytest.raises(InsufficientPermissionsError):
        await guard.can_activate(ctx)


@pytest.mark.asyncio
async def test_guard_runs_object_rule_last():
    guard = RolesGuard()

    def rule(principal, request):
        return principal.claims.get("subject") == "owner"

    @Roles("ops")
    @AuthorizeObject(rule)
    def handler():
        pass

    p_ok = _principal(roles=("ops",))
    p_ok.claims["subject"] = "owner"
    ctx_ok = _FakeCtx(_request(p_ok), object, handler)
    assert await guard.can_activate(ctx_ok) is True

    p_no = _principal(roles=("ops",))
    ctx_no = _FakeCtx(_request(p_no), object, handler)
    with pytest.raises(ForbiddenException):
        await guard.can_activate(ctx_no)


@pytest.mark.asyncio
async def test_guard_merges_class_and_handler_metadata():
    guard = RolesGuard()

    @Roles("admin")
    class Ctrl:
        pass

    @Roles("ops")
    def handler():
        pass

    # principal with "ops" satisfies the union (any-of), not the intersection
    ctx = _FakeCtx(_request(_principal(roles=("ops",))), Ctrl, handler)
    assert await guard.can_activate(ctx) is True


@pytest.mark.asyncio
async def test_deny_undeclared_guard_rejects_handler_without_a_policy():
    class StrictRolesGuard(RolesGuard):
        deny_undeclared = True

    def undeclared():
        pass

    @Roles("ops")
    def declared():
        pass

    strict = StrictRolesGuard()
    with pytest.raises(ForbiddenException):
        await strict.can_activate(_FakeCtx(_request(_principal(roles=("ops",))), object, undeclared))
    assert await strict.can_activate(_FakeCtx(_request(_principal(roles=("ops",))), object, declared)) is True
