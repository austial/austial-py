"""``austial.security`` -- baseline security primitives for Austial apps.

Ships:

- ``SecurityModule.for_root(config)`` -- DI wiring.
- ``SecureHeadersMiddleware`` -- CSP, HSTS, ``X-Content-Type-Options``,
  ``Referrer-Policy``, ``X-Frame-Options``, ``Permissions-Policy``.
- ``RateLimitGuard`` + ``@RateLimit(limit, period_seconds)`` -- fixed-window
  rate limiting keyed on ``(client_ip, route)`` by default, with a pluggable
  ``RateLimitStore`` (in-memory reference impl included).
- ``IdempotencyKeyGuard`` -- ``Idempotency-Key`` replay/conflict handling for
  ``POST``/``PUT``/``PATCH``/``DELETE``, backed by a pluggable
  ``IdempotencyStore``.
- ``CsrfInterceptor`` -- double-submit cookie CSRF check for cookie-authenticated
  flows; skipped when a bearer token is present.
- ``PIIRedactor`` -- masks email, phone, PAN, Aadhaar, passport, IBAN and
  Luhn-verified card numbers.
- ``EnvelopeEncryptor`` -- AES-256-GCM app-level column encryption with an
  embedded KEK version.

Aligned with OWASP ASVS V5 (validation), V6 (secrets/crypto), V8 (data protection),
V9 (transport), and OWASP API Top-10 API4 (unrestricted resource consumption),
API6 (unrestricted access to business flows), API8 (security misconfiguration).
"""

from austial.security.config import SecurityConfig
from austial.security.csrf_interceptor import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    CsrfInterceptor,
)
from austial.security.decorators import RATE_LIMIT_METADATA, RateLimit, get_rate_limit
from austial.security.envelope_encryptor import EnvelopeEncryptor
from austial.security.errors import (
    EncryptionKeyError,
    IdempotencyConflictError,
    RateLimitExceededError,
)
from austial.security.idempotency_guard import IdempotencyKeyGuard
from austial.security.idempotency_store import (
    IdempotencyRecord,
    IdempotencyStore,
    InMemoryIdempotencyStore,
)
from austial.security.pii_redactor import PIIRedactor
from austial.security.rate_limit_guard import RateLimitGuard
from austial.security.rate_limit_store import InMemoryRateLimitStore, RateLimitStore
from austial.security.secure_headers_middleware import SecureHeadersMiddleware
from austial.security.security_module import SecurityModule

__all__ = [
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "CsrfInterceptor",
    "EncryptionKeyError",
    "EnvelopeEncryptor",
    "IdempotencyConflictError",
    "IdempotencyKeyGuard",
    "IdempotencyRecord",
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
    "InMemoryRateLimitStore",
    "PIIRedactor",
    "RATE_LIMIT_METADATA",
    "RateLimit",
    "RateLimitExceededError",
    "RateLimitGuard",
    "RateLimitStore",
    "SecureHeadersMiddleware",
    "SecurityConfig",
    "SecurityModule",
    "get_rate_limit",
]
