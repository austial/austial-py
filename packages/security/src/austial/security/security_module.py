"""``SecurityModule.for_root(...)`` -- wires the security primitives into the DI
container.

Provides ``SecurityConfig``, ``SecureHeadersMiddleware``, ``RateLimitGuard``,
``IdempotencyKeyGuard``, ``CsrfInterceptor``, ``PIIRedactor``, and (when
encryption keys are configured) ``EnvelopeEncryptor``. Registered ``@Global``
by default so any module can inject them.

Callers may override the store implementations by passing a class or a
pre-constructed instance for ``rate_limit_store`` / ``idempotency_store``.
"""

from __future__ import annotations

from typing import Any

from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule
from austial.security.config import SecurityConfig
from austial.security.csrf_interceptor import CsrfInterceptor
from austial.security.envelope_encryptor import EnvelopeEncryptor
from austial.security.idempotency_guard import IdempotencyKeyGuard
from austial.security.idempotency_store import IdempotencyStore, InMemoryIdempotencyStore
from austial.security.pii_redactor import PIIRedactor
from austial.security.rate_limit_guard import RateLimitGuard
from austial.security.rate_limit_store import InMemoryRateLimitStore, RateLimitStore
from austial.security.secure_headers_middleware import SecureHeadersMiddleware


@Module()
class SecurityModule:
    """Import via ``SecurityModule.for_root(config, ...)`` in ``AppModule``'s
    ``imports=[...]``. Registered ``@Global`` by default."""

    @staticmethod
    def for_root(
        config: SecurityConfig | None = None,
        *,
        rate_limit_store: type | RateLimitStore | None = None,
        idempotency_store: type | IdempotencyStore | None = None,
        is_global: bool = True,
    ) -> DynamicModule:
        config = config or SecurityConfig()

        rl_store: RateLimitStore = (
            rate_limit_store if isinstance(rate_limit_store, RateLimitStore) else InMemoryRateLimitStore()
        )
        idem_store: IdempotencyStore = (
            idempotency_store
            if isinstance(idempotency_store, IdempotencyStore)
            else InMemoryIdempotencyStore(ttl_seconds=config.idempotency_ttl_seconds)
        )

        secure_headers = SecureHeadersMiddleware(config)
        redactor = PIIRedactor()
        csrf = CsrfInterceptor()

        providers: list[Any] = [
            {"provide": SecurityConfig, "useValue": config},
            {"provide": RateLimitStore, "useValue": rl_store},
            {"provide": IdempotencyStore, "useValue": idem_store},
            {"provide": SecureHeadersMiddleware, "useValue": secure_headers},
            {"provide": CsrfInterceptor, "useValue": csrf},
            {"provide": PIIRedactor, "useValue": redactor},
            RateLimitGuard,
            IdempotencyKeyGuard,
        ]
        exports: list[Any] = [
            SecurityConfig,
            RateLimitStore,
            IdempotencyStore,
            SecureHeadersMiddleware,
            CsrfInterceptor,
            PIIRedactor,
            RateLimitGuard,
            IdempotencyKeyGuard,
        ]

        if config.active_encryption_key is not None and config.encryption_keys:
            encryptor = EnvelopeEncryptor(
                keys=config.encryption_keys,
                active_key=config.active_encryption_key,
            )
            providers.append({"provide": EnvelopeEncryptor, "useValue": encryptor})
            exports.append(EnvelopeEncryptor)

        return DynamicModule(
            module=SecurityModule,
            providers=providers,
            exports=exports,
        )
