"""``AuthConfig`` -- configuration passed to ``AuthModule.for_root(...)``.

Lives in its own module so ``AuthService`` (which needs the TTLs) can import it
without pulling in ``AuthModule`` (which needs ``AuthService`` in its providers).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class AuthConfig:
    """Every field is required so that a misconfiguration is a startup error,
    not a runtime surprise."""

    jwt_secret: str
    issuer: str
    algorithm: str = "HS256"
    access_ttl: timedelta = timedelta(minutes=15)
    refresh_ttl: timedelta = timedelta(days=14)
    totp_digits: int = 6
    totp_window: int = 1
