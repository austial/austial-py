"""``AuditLogEntry`` -- persisted, append-only shape of an :class:`AuditEvent`.

Declared ``@Entity(append_only=True)`` (see
``austial.orm.decorators.entity.Entity``) so the ``EntityManager`` guard
rejects any ``update()``/``delete()``/``remove()`` against this table --
INSERT is the only mutation the table ever permits. That is what makes the
audit log "WORM" (write-once, read-many) at the application layer;
production deployments should also revoke UPDATE/DELETE at the database
role level, but the framework guard catches the common case.

The ``legal_hold`` column suppresses retention-driven eviction. Once set,
even a row past its retention cutoff is preserved -- this is how
``AuditLogService.evict_older_than`` honours litigation holds without
opening a UPDATE path on the ledger. In practice product code sets
``legal_hold=True`` at insert time for events that are already known to be
subject to a hold; ORMs stronger than this one add a partial-writable
"legal-hold flag" column via a database trigger.
"""

from __future__ import annotations

import datetime as _dt

from austial.orm.decorators.column import Column, PrimaryColumn
from austial.orm.decorators.entity import Entity
from austial.orm.metadata.column_types import DateTime, JSONType, String


@Entity("audit_log", append_only=True)
class AuditLogEntry:
    """The persistent shape of :class:`AuditEvent`. Field types line up 1:1
    with the event, plus ``legal_hold`` for retention suppression."""

    id: str = PrimaryColumn(type_=String(length=64))
    timestamp: _dt.datetime = Column(type_=DateTime(timezone=True), index=True)
    action: str = Column(type_=String(length=255), index=True)
    resource_type: str = Column(type_=String(length=128))
    resource_id: str | None = Column(type_=String(length=128), nullable=True, index=True)
    actor: str | None = Column(type_=String(length=128), nullable=True, index=True)
    tenant_id: str | None = Column(type_=String(length=128), nullable=True, index=True)
    outcome: str = Column(type_=String(length=16))
    request_id: str | None = Column(type_=String(length=128), nullable=True)
    metadata_json: dict = Column(type_=JSONType(), default=None)
    legal_hold: bool = Column(default=False)
