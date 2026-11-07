"""``AuditLogService`` -- the DI-injectable facade over an :class:`AuditStore`.

Product code injects the service, not the store, so the persistence choice
(in-memory, ORM, SIEM push) is a wiring-time decision rather than a
call-site one. The service is deliberately thin -- it does not enrich
events (that's the interceptor's job) and it does not batch (a WORM log
should record every event on its own row).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from austial.audit.config import AuditConfig
from austial.audit.event import AuditEvent
from austial.audit.store import AuditStore
from austial.common.decorators.injectable import Injectable


@Injectable()
class AuditLogService:
    """Record + query events, honour retention policy.

    ``record`` is fire-and-forget from the caller's perspective (the
    coroutine returns once the store has accepted the event); durability
    is the store's responsibility."""

    def __init__(self, store: AuditStore, config: AuditConfig):
        self._store = store
        self._config = config

    async def record(self, event: AuditEvent) -> None:
        await self._store.record(event)

    async def query(
        self,
        *,
        subject: str | None = None,
        actor: str | None = None,
        action: str | None = None,
        tenant_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        return await self._store.query(
            subject=subject,
            actor=actor,
            action=action,
            tenant_id=tenant_id,
            since=since,
            until=until,
            limit=limit,
        )

    async def evict_older_than(self, cutoff: datetime) -> int:
        """Delegate retention-driven eviction to the store. Records under
        legal hold are preserved regardless of ``cutoff``; each store
        implements that guarantee (see :class:`InMemoryAuditStore` for the
        reference behaviour, and :class:`OrmAuditStore` for the WORM-safe
        no-op)."""
        return await self._store.evict_older_than(cutoff)

    async def evict_expired(self, now: datetime | None = None) -> int:
        """Convenience wrapper: eviction relative to the configured
        retention window. Product code typically calls this from a nightly
        scheduled job."""
        anchor = now if now is not None else datetime.now(UTC)
        cutoff = anchor - timedelta(days=self._config.retention_days)
        return await self._store.evict_older_than(cutoff)

    # ------------------------------------------------------------------ #
    # Small helper used by the interceptor -- kept on the service so tests
    # that only exercise ``record`` do not need to import the interceptor.

    @staticmethod
    def build_event(
        *,
        action: str,
        resource_type: str,
        outcome: str = "success",
        resource_id: str | None = None,
        actor: str | None = None,
        tenant_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> AuditEvent:
        return AuditEvent(
            action=action,
            resource_type=resource_type,
            outcome=outcome,  # type: ignore[arg-type]
            resource_id=resource_id,
            actor=actor,
            tenant_id=tenant_id,
            metadata=dict(metadata or {}),
            request_id=request_id,
        )
