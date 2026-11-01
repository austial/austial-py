"""``austial.audit`` -- WORM audit log.

Ships:

- :class:`AuditModule.for_root` -- wires the service + interceptor.
- :class:`AuditLogService` -- injectable facade: ``record()``, ``query()``,
  ``evict_older_than()``.
- :class:`AuditEvent` -- frozen dataclass, one entry.
- :class:`AuditLogEntry` -- ``@Entity(append_only=True)`` shape used by
  :class:`OrmAuditStore`.
- ``@Audited(action, resource_type=..., resource_id_from=..., capture_result=...)``
  -- metadata decorator + :class:`AuditedInterceptor`.
- :class:`AuditStore` protocol + :class:`InMemoryAuditStore` +
  :class:`OrmAuditStore`.
- :class:`AuditConfig` -- retention (default 5 years, per IFSCA AML rule 10.1).

Designed against OWASP ASVS V7 (Logging and Error Handling) and ISO/IEC
27001 Annex A.5.24 / A.8.15 -- the framework guarantees append-only writes
and honours legal holds; the product supplies the persistence, the SIEM
forwarding, and the retention job.
"""

from austial.audit.audit_module import AuditModule
from austial.audit.config import AuditConfig
from austial.audit.decorators import AUDITED_METADATA, Audited, AuditSpec, get_audit_spec
from austial.audit.entity import AuditLogEntry
from austial.audit.errors import AuditError, AuditStoreUnavailableError, LegalHoldViolationError
from austial.audit.event import AuditEvent, Outcome
from austial.audit.interceptor import AuditedInterceptor
from austial.audit.service import AuditLogService
from austial.audit.store import AuditStore, InMemoryAuditStore, OrmAuditStore

__all__ = [
    "AUDITED_METADATA",
    "Audited",
    "AuditConfig",
    "AuditEvent",
    "AuditError",
    "AuditLogEntry",
    "AuditLogService",
    "AuditModule",
    "AuditSpec",
    "AuditStore",
    "AuditStoreUnavailableError",
    "AuditedInterceptor",
    "InMemoryAuditStore",
    "LegalHoldViolationError",
    "OrmAuditStore",
    "Outcome",
    "get_audit_spec",
]
