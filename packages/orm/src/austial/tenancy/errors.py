"""Tenancy-specific exceptions."""

from __future__ import annotations

from austial.common.exceptions import ForbiddenException


class MissingTenantError(ForbiddenException):
    """Raised when a request that requires a tenant lacks one."""

    def __init__(self, message: str = "Tenant context is required"):
        super().__init__(message)


class TenantMismatchError(ForbiddenException):
    """Raised when an operation targets a tenant other than the caller's."""

    def __init__(self, expected: str, actual: str):
        super().__init__(f"Tenant mismatch: expected {expected!r}, got {actual!r}")
