"""``AuthService`` -- orchestrates login/refresh/logout on top of the strategies.

The service is agnostic to the user model: the product calls
``verify_password(...)`` with the stored hash it already loaded from its user
table, and ``issue_tokens(subject, claims)`` to mint the access + refresh pair.
This keeps the framework decoupled from persistence.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from austial.auth.argon2_hasher import PasswordHasher, PasswordVerificationError
from austial.auth.config import AuthConfig
from austial.auth.errors import AuthenticationError, MfaRequiredError
from austial.auth.jwt_strategy import JwtStrategy
from austial.auth.refresh_token_store import RefreshTokenRecord, RefreshTokenStore
from austial.auth.totp_strategy import TotpStrategy
from austial.common.decorators.injectable import Injectable

#: ``claims`` for :meth:`AuthService.refresh` may be a callable that receives the *rotated* token's record
#: and returns the access-token claims (sync or async). Needed because the claims usually depend on what
#: the record points at (its session, the subject's current tenant/roles), which is only known once the
#: refresh token has been resolved.
ClaimsProvider = Callable[[RefreshTokenRecord], dict[str, Any] | Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class TokenPair:
    """Returned to the caller on login/refresh."""

    access_token: str
    refresh_token: str
    expires_in_seconds: int


@Injectable()
class AuthService:
    def __init__(
        self,
        jwt: JwtStrategy,
        totp: TotpStrategy,
        hasher: PasswordHasher,
        refresh_store: RefreshTokenStore,
        config: AuthConfig,
    ) -> None:
        self._jwt = jwt
        self._totp = totp
        self._hasher = hasher
        self._refresh_store = refresh_store
        self._config = config

    def verify_password(self, password: str, encoded: str) -> None:
        """Raise ``AuthenticationError`` on any mismatch. Never leak which failure."""
        try:
            self._hasher.verify(password, encoded)
        except PasswordVerificationError as exc:
            raise AuthenticationError("invalid credentials") from exc

    def require_mfa(self, secret: str, code: str | None) -> None:
        """Raise ``MfaRequiredError`` if MFA is enrolled and ``code`` is missing or invalid."""
        if secret and not (code and self._totp.verify(secret, code)):
            raise MfaRequiredError()

    async def issue_tokens(
        self, subject: str, *, claims: dict[str, Any] | None = None, session_id: str | None = None
    ) -> TokenPair:
        access = self._jwt.sign(subject, claims=claims)
        opaque, _ = await self._refresh_store.issue(subject, ttl=self._config.refresh_ttl, session_id=session_id)
        return TokenPair(
            access_token=access,
            refresh_token=opaque,
            expires_in_seconds=int(self._config.access_ttl.total_seconds()),
        )

    async def refresh(
        self, opaque_refresh_token: str, *, claims: dict[str, Any] | ClaimsProvider | None = None
    ) -> TokenPair:
        """Rotate the refresh token and mint a fresh access token.

        ``claims`` is either a fixed dict or a ``ClaimsProvider`` called with the rotated token's
        ``RefreshTokenRecord`` -- use the latter to derive the claims from the record's ``session_id`` /
        ``subject`` (an exception raised by the provider, e.g. ``AuthenticationError`` for a
        deactivated account, propagates to the caller)."""
        try:
            new_opaque, record = await self._refresh_store.rotate(opaque_refresh_token, ttl=self._config.refresh_ttl)
        except LookupError as exc:
            raise AuthenticationError("invalid refresh token") from exc

        resolved: dict[str, Any] | None
        if callable(claims):
            produced = claims(record)
            resolved = await produced if inspect.isawaitable(produced) else produced
        else:
            resolved = claims
        access = self._jwt.sign(record.subject, claims=resolved)
        return TokenPair(
            access_token=access,
            refresh_token=new_opaque,
            expires_in_seconds=int(self._config.access_ttl.total_seconds()),
        )

    async def logout(self, opaque_refresh_token: str) -> None:
        await self._refresh_store.revoke(opaque_refresh_token)

    async def logout_everywhere(self, subject: str) -> int:
        """Revoke every refresh token for ``subject`` (password change, MFA re-enrol,
        admin action)."""
        return await self._refresh_store.revoke_all_for_subject(subject)
