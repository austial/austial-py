"""``SecurityConfig`` -- configuration passed to ``SecurityModule.for_root(...)``.

Held in its own module so ``EnvelopeEncryptor``/``RateLimitGuard``/etc. can read
individual fields without importing the module wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SecurityConfig:
    """Every field has a safe default; only ``encryption_keys`` + ``active_encryption_key``
    must be supplied for the ``EnvelopeEncryptor`` to be usable."""

    csp: str = "default-src 'self'; frame-ancestors 'none'; upgrade-insecure-requests"
    hsts_max_age: int = 31536000
    permissions_policy: str = "geolocation=(), microphone=(), camera=()"
    encryption_keys: dict[str, bytes] = field(default_factory=dict)
    active_encryption_key: str | None = None
    default_rate_limit: tuple[int, int] = (60, 60)
    idempotency_ttl_seconds: int = 86400
    trusted_proxy_hops: int = 0
    """How many reverse proxies you operate in front of the app, for client-IP resolution.

    ``0`` (default): ``X-Forwarded-For`` is ignored and the socket peer is the client -- correct when
    the app is exposed directly, and safe by default because the header is client-controlled. ``n > 0``:
    the client is the ``n``-th entry counted from the *right* of ``X-Forwarded-For`` (each trusted proxy
    appends the address it received the request from, so the right-most ``n`` entries are trustworthy
    and everything to their left is attacker-controlled)."""
