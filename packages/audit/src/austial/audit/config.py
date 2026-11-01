"""``AuditConfig`` -- configuration for :class:`AuditModule`.

Lives in its own module so the injectable service and the module wiring can
both import it without circular-import gymnastics (same pattern as
``austial.auth.config``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuditConfig:
    """Retention window for the WORM audit log.

    ``retention_days`` defaults to 1825 (5 years) which matches the minimum
    record-retention period the IFSCA AML/CFT Guidelines require of regulated
    entities (rule 10.1 -- "records shall be maintained for a minimum period
    of five years"). Product code overrides for jurisdictions with stricter
    rules; the framework never silently trims below the default."""

    retention_days: int = 1825
