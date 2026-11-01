"""``JwtStrategy`` -- short-lived HS256 access tokens (default 15 min).

Design notes:

- **Access tokens are the JWT.** They are short-lived and self-contained: the app can
  authenticate a request from the token alone, without a database call.
- **Refresh tokens are NOT JWTs**; they are opaque strings persisted in a
  ``RefreshTokenStore`` so that they can be revoked. This is issued and rotated by
  ``AuthService``, not here -- ``JwtStrategy`` only signs/verifies JWTs.
- Signing uses HS256 by default (the config supplies the secret). Callers who need
  RS256 pass ``algorithm="RS256"`` and a PEM key pair; the strategy stays the same.
- Every token carries ``iss``, ``iat``, ``exp``, ``jti``, and application claims. The
  ``jti`` gives you the hook for token-level revocation if you ever want it, without
  changing the wire format.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt as _jwt

from austial.auth.errors import InvalidTokenError, TokenExpiredError
from austial.common.decorators.injectable import Injectable


@dataclass(frozen=True, slots=True)
class TokenPayload:
    """Decoded JWT contents surfaced to callers.

    ``subject`` is the user identifier; ``claims`` is the application-defined payload
    (tenant id, roles, session id -- whatever was passed to ``sign()``). System claims
    (``iss``, ``iat``, ``exp``, ``jti``) are surfaced as top-level fields.
    """

    subject: str
    claims: dict[str, Any] = field(default_factory=dict)
    issuer: str | None = None
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    token_id: str | None = None


@Injectable()
class JwtStrategy:
    """Signs and verifies HS256/RS256 access tokens."""

    def __init__(
        self,
        *,
        secret: str,
        issuer: str,
        algorithm: str = "HS256",
        access_ttl: timedelta = timedelta(minutes=15),
        clock_skew_seconds: int = 30,
    ) -> None:
        if not secret or len(secret) < 32:
            raise ValueError("JWT secret must be at least 32 characters (see OWASP ASVS V6)")
        self._secret = secret
        self._issuer = issuer
        self._algorithm = algorithm
        self._access_ttl = access_ttl
        self._clock_skew_seconds = clock_skew_seconds

    def sign(self, subject: str, claims: dict[str, Any] | None = None, *, ttl: timedelta | None = None) -> str:
        """Sign a JWT for ``subject`` with application ``claims``.

        Passing ``ttl`` overrides the strategy default (useful for step-up MFA
        tokens or short-lived one-time actions)."""
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            **(claims or {}),
            "iss": self._issuer,
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int((now + (ttl or self._access_ttl)).timestamp()),
            "jti": secrets.token_urlsafe(16),
        }
        return _jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def verify(self, token: str) -> TokenPayload:
        """Verify ``token``; raise ``TokenExpiredError`` or ``InvalidTokenError`` on failure.

        The caller decides what to do with the decoded payload; this method never
        touches the database and is safe to call from a guard."""
        try:
            data = _jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                leeway=self._clock_skew_seconds,
            )
        except _jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError() from exc
        except _jwt.InvalidTokenError as exc:  # covers signature, issuer, malformed
            raise InvalidTokenError(str(exc)) from exc

        subject = data.pop("sub", None)
        if subject is None:
            raise InvalidTokenError("token missing 'sub' claim")

        issuer = data.pop("iss", None)
        iat = data.pop("iat", None)
        exp = data.pop("exp", None)
        jti = data.pop("jti", None)

        return TokenPayload(
            subject=str(subject),
            claims=data,
            issuer=issuer,
            issued_at=datetime.fromtimestamp(iat, UTC) if iat is not None else None,
            expires_at=datetime.fromtimestamp(exp, UTC) if exp is not None else None,
            token_id=jti,
        )
