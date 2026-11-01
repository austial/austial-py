"""``AuthModule.for_root(...)`` -- wires ``JwtStrategy``, ``TotpStrategy``,
``Argon2Hasher``, ``AuthGuard`` and (optionally) an in-memory refresh-token store
into the DI container.

Product code overrides the refresh-token store with a persistent implementation
by passing ``refresh_token_store=MyPersistentStore``.
"""

from __future__ import annotations

from typing import Any

from austial.auth.argon2_hasher import Argon2Hasher, PasswordHasher
from austial.auth.auth_guard import AuthGuard
from austial.auth.auth_service import AuthService
from austial.auth.config import AuthConfig
from austial.auth.jwt_strategy import JwtStrategy
from austial.auth.refresh_token_store import InMemoryRefreshTokenStore, RefreshTokenStore
from austial.auth.totp_strategy import TotpStrategy
from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule


@Module()
class AuthModule:
    """Import via ``AuthModule.for_root(config, refresh_token_store=...)`` in ``AppModule``'s
    ``imports=[...]``. Registered ``@Global`` by default so any module can inject
    ``JwtStrategy``, ``TotpStrategy``, ``PasswordHasher``, ``AuthService`` and ``AuthGuard``."""

    @staticmethod
    def for_root(
        config: AuthConfig,
        *,
        refresh_token_store: type | RefreshTokenStore | None = None,
        password_hasher: type | PasswordHasher | None = None,
        is_global: bool = True,
    ) -> DynamicModule:
        jwt = JwtStrategy(
            secret=config.jwt_secret,
            issuer=config.issuer,
            algorithm=config.algorithm,
            access_ttl=config.access_ttl,
        )
        totp = TotpStrategy(
            issuer=config.issuer,
            digits=config.totp_digits,
            window=config.totp_window,
        )
        hasher: PasswordHasher = (
            Argon2Hasher() if password_hasher is None or isinstance(password_hasher, type) else password_hasher
        )
        # A class (not an instance) is registered with ``useClass`` so the container can inject its own
        # dependencies -- a persistent store needs repositories, which do not exist before DI runs.
        store_provider: Any = (
            {"provide": RefreshTokenStore, "useClass": refresh_token_store}
            if isinstance(refresh_token_store, type)
            else {"provide": RefreshTokenStore, "useValue": refresh_token_store or InMemoryRefreshTokenStore()}
        )
        hasher_provider: Any = (
            {"provide": PasswordHasher, "useClass": password_hasher}
            if isinstance(password_hasher, type)
            else {"provide": PasswordHasher, "useValue": hasher}
        )

        providers: list[Any] = [
            {"provide": JwtStrategy, "useValue": jwt},
            {"provide": TotpStrategy, "useValue": totp},
            hasher_provider,
            {"provide": Argon2Hasher, "useValue": hasher if isinstance(hasher, Argon2Hasher) else Argon2Hasher()},
            store_provider,
            {"provide": AuthConfig, "useValue": config},
            AuthService,
            AuthGuard,
        ]

        return DynamicModule(
            module=AuthModule,
            providers=providers,
            exports=[
                JwtStrategy,
                TotpStrategy,
                PasswordHasher,
                Argon2Hasher,
                RefreshTokenStore,
                AuthConfig,
                AuthService,
                AuthGuard,
            ],
        )
