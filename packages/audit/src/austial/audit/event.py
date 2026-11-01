"""``AuditEvent`` -- the in-memory shape of one audit-log entry.

An event is the abstract, ORM-free representation. ``AuditLogEntry``
(``entity.py``) is the persisted shape used by ``OrmAuditStore``. Keeping
them separate lets ``AuditLogService`` be exercised in tests against an
in-memory store without ever booting a database.

The dataclass is frozen + slotted for two reasons:

- **Immutability up the stack.** Once an event has been recorded, no code
  path should mutate it. A frozen dataclass makes accidental writes a
  ``FrozenInstanceError`` rather than a silent tamper.
- **Cache-friendly attribute access.** Slots skip the per-instance dict and
  keep events cheap in high-volume paths (login, transactions, admin ops).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

Outcome = Literal["success", "failure"]


def _new_event_id() -> str:
    """UUIDv4 as an unambiguous global identifier -- an audit event's id must
    survive replication and export to external SIEMs without colliding."""
    return str(uuid.uuid4())


def _now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One immutable, timestamped record of an action taken against a
    resource. Every field is populated at construction time; ``record()`` is
    only ever handed fully-formed events.

    Field semantics:

    - ``id`` -- server-generated UUIDv4; product code never sets it.
    - ``timestamp`` -- UTC clock reading at the moment of the event.
    - ``actor`` -- the authenticated principal's subject id. ``None`` for
      system-initiated actions (a background job, a scheduled task).
    - ``tenant_id`` -- populated from ``request.state.tenant`` when
      ``austial.tenancy`` is wired; ``None`` on single-tenant deployments.
    - ``action`` -- dot-namespaced short verb, e.g. ``"funds.create"``,
      ``"user.login.mfa_failure"``. Namespacing keeps SIEM queries tractable.
    - ``resource_type`` -- e.g. ``"Fund"``, ``"UserAccount"``.
    - ``resource_id`` -- optional; ``None`` for actions where the resource
      does not yet exist (a failed sign-in, a list-view read).
    - ``outcome`` -- ``"success"`` or ``"failure"``.
    - ``metadata`` -- caller-supplied context; do not put PII or secrets in
      here. The interceptor puts request path + failure class name here.
    - ``request_id`` -- the correlation id from
      ``request.state.request_id`` (typically set by ``LoggingMiddleware``)
      so an event can be joined to the corresponding access log line.
    """

    action: str
    resource_type: str
    outcome: Outcome = "success"
    resource_id: str | None = None
    actor: str | None = None
    tenant_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    id: str = field(default_factory=_new_event_id)
    timestamp: datetime = field(default_factory=_now_utc)
