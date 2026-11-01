"""Audit-log-specific exceptions.

Extends the framework's canonical HTTP exception hierarchy so
``AllExceptionsFilter`` maps them to the right status code without a
translation layer, and each has a distinct type so product filters can
render a domain-specific response body when they want to.
"""

from __future__ import annotations

from austial.common.exceptions import HttpException


class AuditError(HttpException):
    """Base class for every failure raised by ``austial.audit``.

    Defaults to 500 -- audit failures are server-side problems, not caller
    errors -- but subclasses may narrow it."""

    def __init__(self, message: str = "Audit log failure", status_code: int = 500):
        super().__init__(message, status_code)


class AuditStoreUnavailableError(AuditError):
    """The persistent store is unreachable or refused the write."""

    def __init__(self, message: str = "Audit store unavailable"):
        super().__init__(message=message, status_code=503)


class LegalHoldViolationError(AuditError):
    """Raised when retention eviction is asked to remove a record that
    carries an active legal hold. Suppression is silent by default -- the
    service just skips those rows -- so this is only raised when product
    code opts into strict eviction and needs to see the guarded rows."""

    def __init__(self, count: int):
        super().__init__(
            message=f"Eviction refused: {count} record(s) under legal hold",
            status_code=409,
        )
        self.count = count
