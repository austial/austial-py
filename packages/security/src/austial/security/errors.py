"""Security-specific exceptions.

Extend Austial's typed HTTP exceptions so ``AllExceptionsFilter`` maps them to
the correct status codes without a translation layer.
"""

from __future__ import annotations

from austial.common.exceptions import ConflictException, TooManyRequestsException


class RateLimitExceededError(TooManyRequestsException):
    """Raised by ``RateLimitGuard`` when a caller exceeds their allowance
    inside the current fixed window (HTTP 429)."""

    def __init__(self, message: str = "Rate limit exceeded", *, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class IdempotencyConflictError(ConflictException):
    """Raised by ``IdempotencyKeyGuard`` when the same ``Idempotency-Key`` is
    replayed with a different request body inside the TTL (HTTP 409)."""

    def __init__(self, message: str = "Idempotency key reused with different request"):
        super().__init__(message)


class EncryptionKeyError(ValueError):
    """Raised by ``EnvelopeEncryptor`` when the active KEK is missing, a key
    length is wrong, or a stored ciphertext references an unknown key version."""
