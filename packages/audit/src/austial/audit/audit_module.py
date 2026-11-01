"""``AuditModule.for_root(config, store=...)`` -- wires the audit stack.

Provides:

- :class:`AuditLogService` -- the injectable facade.
- :class:`AuditedInterceptor` -- the interceptor that fires on
  ``@Audited(...)``-marked handlers.
- :class:`AuditConfig` -- the retention window.
- :class:`AuditStore` -- defaults to :class:`InMemoryAuditStore`; product
  code passes an ``OrmAuditStore`` (or a SIEM-backed implementation) in
  ``store=`` to opt into durable persistence.

Registered ``@Global`` by default so the interceptor and service are
injectable from every module without a re-import in each one -- audit is
a cross-cutting concern.
"""

from __future__ import annotations

from typing import Any

from austial.audit.config import AuditConfig
from austial.audit.interceptor import AuditedInterceptor
from austial.audit.service import AuditLogService
from austial.audit.store import AuditStore, InMemoryAuditStore
from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule


@Module()
class AuditModule:
    """Import via ``AuditModule.for_root(config, store=MyStore())`` in
    ``AppModule``'s ``imports=[...]``. When ``store`` is omitted an
    :class:`InMemoryAuditStore` is provided -- fine for tests, unsafe for
    production because it does not survive a process restart."""

    @staticmethod
    def for_root(
        config: AuditConfig | None = None,
        *,
        store: AuditStore | None = None,
        is_global: bool = True,
    ) -> DynamicModule:
        resolved_config = config if config is not None else AuditConfig()
        resolved_store: AuditStore = store if store is not None else InMemoryAuditStore()

        providers: list[Any] = [
            {"provide": AuditConfig, "useValue": resolved_config},
            {"provide": AuditStore, "useValue": resolved_store},
            AuditLogService,
            AuditedInterceptor,
        ]

        return DynamicModule(
            module=AuditModule,
            providers=providers,
            exports=[
                AuditConfig,
                AuditStore,
                AuditLogService,
                AuditedInterceptor,
            ],
        )
