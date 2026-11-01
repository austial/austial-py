"""Audit-log store contract + reference implementations.

The service ``AuditLogService`` is store-agnostic; product code chooses:

- :class:`InMemoryAuditStore` -- reference implementation for tests and
  local dev. Keeps events in a list; queries do a linear scan (fine for
  ~thousands of events during a test run).
- :class:`OrmAuditStore` -- persists via a ``Repository[AuditLogEntry]``.
  Delegates all mutation to the append-only ORM entity, so an accidental
  ``update()``/``delete()`` from anywhere in the codebase is rejected by
  the entity manager (see ``austial.orm.exceptions.AppendOnlyViolationError``).

Product code implements its own :class:`AuditStore` when it wants to write
directly to a SIEM (Splunk HEC, an S3-backed WORM bucket, etc.) instead of
a relational table.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from austial.audit.entity import AuditLogEntry
from austial.audit.event import AuditEvent
from austial.common.decorators.injectable import Injectable


@runtime_checkable
class AuditStore(Protocol):
    """Persistence contract for :class:`AuditLogService`. Only append (``record``),
    query, and retention-driven eviction are ever called -- updates are
    impossible by design."""

    async def record(self, event: AuditEvent) -> None: ...

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
    ) -> list[AuditEvent]: ...

    async def evict_older_than(self, cutoff: datetime) -> int:
        """Remove events with ``timestamp < cutoff`` that do NOT carry a
        legal hold. Returns the count evicted. Implementations that back
        immutable storage (S3 Object Lock, WORM tape) can no-op this and
        rely on the storage layer's own expiry."""
        ...


@Injectable()
class InMemoryAuditStore:
    """In-memory reference implementation -- an insert-only list. Suitable
    for tests and local development; NOT suitable for production because it
    is not durable, not shared across processes, and holds a hard reference
    to every event for the process lifetime.

    ``legal_hold`` is carried on a shadow map -- the event dataclass itself
    is immutable (``frozen=True``), so per-record legal-hold state lives
    beside it here rather than inside it. Product callers set the hold via
    :meth:`set_legal_hold` before eviction runs.
    """

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._holds: set[str] = set()

    async def record(self, event: AuditEvent) -> None:
        # A defensive copy is not required -- events are frozen dataclasses.
        self._events.append(event)

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
        # ``subject`` is an alias for ``actor`` -- the brief documents both
        # spellings on the service call.
        actor_filter = actor if actor is not None else subject
        results: list[AuditEvent] = []
        for event in self._events:
            if actor_filter is not None and event.actor != actor_filter:
                continue
            if action is not None and event.action != action:
                continue
            if tenant_id is not None and event.tenant_id != tenant_id:
                continue
            if since is not None and event.timestamp < since:
                continue
            if until is not None and event.timestamp > until:
                continue
            results.append(event)
            if len(results) >= limit:
                break
        return results

    async def evict_older_than(self, cutoff: datetime) -> int:
        keep: list[AuditEvent] = []
        evicted = 0
        for event in self._events:
            if event.timestamp < cutoff and event.id not in self._holds:
                evicted += 1
                continue
            keep.append(event)
        self._events = keep
        return evicted

    def set_legal_hold(self, event_id: str, *, hold: bool = True) -> None:
        """Toggle the legal-hold flag for one event id. Not part of the
        :class:`AuditStore` protocol (persistent stores set the flag through
        their own admin path)."""
        if hold:
            self._holds.add(event_id)
        else:
            self._holds.discard(event_id)


def _entry_from_event(event: AuditEvent, *, legal_hold: bool = False) -> AuditLogEntry:
    """Translate an :class:`AuditEvent` into an :class:`AuditLogEntry` for
    persistence. Kept private so callers cannot accidentally construct an
    entry with an id that does not match its event."""
    return AuditLogEntry(
        id=event.id,
        timestamp=event.timestamp,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        actor=event.actor,
        tenant_id=event.tenant_id,
        outcome=event.outcome,
        metadata_json=dict(event.metadata),
        request_id=event.request_id,
        legal_hold=legal_hold,
    )


def _event_from_entry(entry: AuditLogEntry) -> AuditEvent:
    return AuditEvent(
        id=entry.id,
        timestamp=entry.timestamp,
        action=entry.action,
        resource_type=entry.resource_type,
        resource_id=entry.resource_id,
        actor=entry.actor,
        tenant_id=entry.tenant_id,
        outcome=entry.outcome,  # type: ignore[arg-type]
        metadata=dict(entry.metadata_json or {}),
        request_id=entry.request_id,
    )


@Injectable()
class OrmAuditStore:
    """ORM-backed :class:`AuditStore` -- writes an :class:`AuditLogEntry`
    per event. Since ``AuditLogEntry`` is ``append_only=True``, the entity
    manager rejects any attempt to update or delete a row -- eviction is
    therefore only possible via the entity manager's ``delete()`` which is
    blocked. Production deployments that need retention-driven eviction
    handle it out-of-band (e.g. per-partition ``DROP TABLE`` from a
    scheduled job that first checks ``legal_hold``); this method returns 0
    on this store so callers do not treat it as a silent no-op."""

    def __init__(self, repository: Any):
        # Typed loosely as ``Any`` so the store can be constructed with any
        # object exposing the ``Repository[AuditLogEntry]`` shape (real or
        # mocked). This matters because ``OrmAuditStore`` is exercised in
        # unit tests without booting a real ``DataSource``.
        self._repository = repository

    async def record(self, event: AuditEvent) -> None:
        entry = _entry_from_event(event)
        # ``insert`` (not ``save``): the event id is the primary key and is always pre-set, and
        # ``save`` would treat that as an UPDATE of an existing row, which the append-only guard rejects.
        await self._repository.insert(entry)

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
        criteria: dict[str, Any] = {}
        actor_filter = actor if actor is not None else subject
        if actor_filter is not None:
            criteria["actor"] = actor_filter
        if action is not None:
            criteria["action"] = action
        if tenant_id is not None:
            criteria["tenant_id"] = tenant_id
        # ``since``/``until`` and ``limit`` require the query-builder path;
        # keep the store's default read simple and let product code drop
        # into ``Repository.create_query_builder`` for range-scan reports.
        rows: list[AuditLogEntry] = (
            await self._repository.find_by(criteria) if criteria else await self._repository.find()
        )
        events = [_event_from_entry(row) for row in rows]
        if since is not None:
            events = [e for e in events if e.timestamp >= since]
        if until is not None:
            events = [e for e in events if e.timestamp <= until]
        return events[:limit]

    async def evict_older_than(self, cutoff: datetime) -> int:
        # See class docstring -- eviction is a database-admin operation on
        # an append-only entity, not an ORM call.
        return 0
