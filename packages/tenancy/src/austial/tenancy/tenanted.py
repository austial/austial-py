"""``Tenanted`` -- entity mixin adding a ``tenant_id`` column.

Add to any entity that must be scoped to a tenant. The column is a required
string (raises at flush time if unset) so a row without a tenant is a hard
persistence error rather than a silent write to the wrong table.

Product code sets ``tenant_id`` explicitly at insert (typically from
``TenantContext.require().tenant_id`` in the service that creates the row),
which keeps the write path auditable. On read, the repository or service
filters by ``tenant_id`` -- ``TenantGuard`` guarantees the value exists.
"""

from __future__ import annotations

from austial.orm.decorators.column import Column


class Tenanted:
    """Mixin -- inherit alongside your ``@Entity()``-decorated dataclass to add
    a ``tenant_id`` column. Order matters: put ``Tenanted`` before other
    mixins but after your primary-key column."""

    tenant_id: str = Column(nullable=False, index=True)
