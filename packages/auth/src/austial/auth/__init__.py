"""``austial.auth`` -- authentication primitives.

Ships an ``AuthModule.for_root(...)`` dynamic module, an ``Argon2Hasher`` (OWASP-recommended
password hashing), a ``JwtStrategy`` (short-lived access + opaque rotating refresh tokens),
a ``TotpStrategy`` (RFC 6238 MFA), an ``AuthGuard`` (bearer-token verification), the
``@Public`` decorator to skip that guard, and a ``CurrentUser`` param decorator to inject
the authenticated principal into a handler. The product supplies the user model and the
persistent refresh-token store (an in-memory default is provided for tests).

Design mirrors ``@nestjs/passport`` + ``@nestjs/jwt``: the framework provides *strategies*
and *guards*; product wires them together against its own user entity. Everything is
side-effect-free and testable in isolation.
"""

from austial.auth.argon2_hasher import Argon2Hasher, PasswordHasher, PasswordVerificationError
from austial.auth.auth_guard import AuthGuard, AuthPrincipal
from austial.auth.auth_module import AuthModule
from austial.auth.auth_service import AuthService
from austial.auth.config import AuthConfig
from austial.auth.decorators import IS_PUBLIC_METADATA, CurrentUser, Public
from austial.auth.errors import (
    AuthenticationError,
    InvalidTokenError,
    MfaRequiredError,
    TokenExpiredError,
)
from austial.auth.jwt_strategy import JwtStrategy, TokenPayload
from austial.auth.oauth import (
    AuthorizationRequest,
    GitHubOAuth,
    GoogleOAuth,
    MicrosoftOAuth,
    OAuth2Provider,
    OAuthError,
    OAuthTokens,
    generate_state,
    verify_state,
)
from austial.auth.refresh_token_store import (
    InMemoryRefreshTokenStore,
    RefreshTokenRecord,
    RefreshTokenStore,
)
from austial.auth.totp_strategy import TotpStrategy

__all__ = [
    "AuthorizationRequest",
    "GitHubOAuth",
    "GoogleOAuth",
    "MicrosoftOAuth",
    "OAuth2Provider",
    "OAuthError",
    "OAuthTokens",
    "generate_state",
    "verify_state",
    "Argon2Hasher",
    "AuthConfig",
    "AuthenticationError",
    "AuthGuard",
    "AuthModule",
    "AuthPrincipal",
    "AuthService",
    "CurrentUser",
    "InMemoryRefreshTokenStore",
    "InvalidTokenError",
    "IS_PUBLIC_METADATA",
    "JwtStrategy",
    "MfaRequiredError",
    "PasswordHasher",
    "PasswordVerificationError",
    "Public",
    "RefreshTokenRecord",
    "RefreshTokenStore",
    "TokenExpiredError",
    "TokenPayload",
    "TotpStrategy",
]
