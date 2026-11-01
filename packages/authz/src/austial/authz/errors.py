"""Authorisation-specific exceptions -- 403 with sub-types for observability."""

from __future__ import annotations

from austial.common.exceptions import ForbiddenException


class InsufficientRolesError(ForbiddenException):
    def __init__(self, required: tuple[str, ...], actual: tuple[str, ...]):
        super().__init__(f"Missing required role(s): {list(required)}")
        self.required = required
        self.actual = actual


class InsufficientPermissionsError(ForbiddenException):
    def __init__(self, required: tuple[str, ...], actual: tuple[str, ...]):
        super().__init__(f"Missing required permission(s): {list(required)}")
        self.required = required
        self.actual = actual
