"""``OneToOne()``/``OneToMany()``/``ManyToOne()``/``ManyToMany()`` + ``JoinColumn``/``JoinTable``
-- mirrors TypeORM's relation decorators.

**Deliberate API-shape deviation from TypeORM**: TypeORM stacks ``@JoinColumn()``/``@JoinTable()``
as a *separate* decorator above ``@ManyToOne()``/``@ManyToMany()`` on the same class property.
Python's "marker-as-default-value" trick (the same one ``Inject()``/``Column()`` use, since Python
has no field-level decorators) only allows a single right-hand-side expression per attribute --
there is no way to stack two independent decorator calls over one annotated assignment. So
``JoinColumn``/``JoinTable`` become plain dataclasses passed as a **keyword argument** into the
relation marker instead::

    owner: User = ManyToOne(lambda: User, join_column=JoinColumn(name="owner_id"))

This is intentional, not an oversight.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from austial.orm.metadata.entity_metadata import JoinColumnMetadata, JoinTableMetadata, RelationType

Target = type | Callable[[], type]


@dataclass
class JoinColumn:
    """Declares the owning side's foreign-key column. Pass into ``OneToOne``/``ManyToOne``."""

    name: str | None = None
    referenced_column_name: str = "id"

    def to_metadata(self) -> JoinColumnMetadata:
        return JoinColumnMetadata(name=self.name, referenced_column_name=self.referenced_column_name)


@dataclass
class JoinTable:
    """Declares the owning side of a ``ManyToMany`` relation -- a join table gets generated."""

    name: str | None = None
    join_column_name: str | None = None
    inverse_join_column_name: str | None = None

    def to_metadata(self) -> JoinTableMetadata:
        return JoinTableMetadata(
            name=self.name,
            join_column_name=self.join_column_name,
            inverse_join_column_name=self.inverse_join_column_name,
        )


class RelationMarker:
    __slots__ = (
        "relation_type",
        "target",
        "inverse_side",
        "nullable",
        "on_delete",
        "cascade",
        "join_column",
        "join_table",
        "default",
        "default_factory",
    )

    def __init__(
        self,
        relation_type: RelationType,
        target: Target,
        inverse_side: str | None = None,
        *,
        nullable: bool = True,
        on_delete: str | None = None,
        cascade: bool = False,
        join_column: JoinColumn | None = None,
        join_table: JoinTable | None = None,
        default: Any = None,
        default_factory: Callable[[], Any] | None = None,
    ):
        self.relation_type = relation_type
        self.target = target
        self.inverse_side = inverse_side
        self.nullable = nullable
        self.on_delete = on_delete
        self.cascade = cascade
        self.join_column = join_column
        self.join_table = join_table
        self.default = default
        self.default_factory = default_factory

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"RelationMarker({self.relation_type})"


def target_resolver(target: Target) -> Callable[[], type]:
    """Normalizes a relation's ``target`` (either the entity class directly, or a zero-arg
    callable like ``lambda: Comment`` for forward references) into a callable, so
    ``RelationMetadata.target_resolver`` always has one uniform shape to call lazily."""
    if isinstance(target, type):
        return lambda: target
    return target


def OneToOne(
    target: Target,
    inverse_side: str | None = None,
    *,
    join_column: JoinColumn | None = None,
    nullable: bool = True,
    on_delete: str | None = None,
    default: Any = None,
) -> Any:
    return RelationMarker(
        RelationType.ONE_TO_ONE,
        target,
        inverse_side,
        nullable=nullable,
        on_delete=on_delete,
        join_column=join_column,
        default=default,
    )


def OneToMany(
    target: Target, inverse_side: str, *, cascade: bool = False, default_factory: Callable[[], Any] = list
) -> Any:
    """Always the non-owning side -- ``inverse_side`` (the attribute name on the *target* entity
    holding the matching ``ManyToOne``) is mandatory, exactly as in TypeORM. ``default_factory``
    seeds the attribute before any relations are eagerly loaded (an empty list by default, mirroring
    TypeORM's own to-many attributes)."""
    return RelationMarker(
        RelationType.ONE_TO_MANY, target, inverse_side, nullable=True, cascade=cascade, default_factory=default_factory
    )


def ManyToOne(
    target: Target,
    inverse_side: str | None = None,
    *,
    join_column: JoinColumn | None = None,
    nullable: bool = True,
    on_delete: str | None = "CASCADE",
    default: Any = None,
) -> Any:
    """Always the owning side -- generates a foreign-key column (default name derived by the
    naming strategy from the attribute name if ``join_column`` isn't given)."""
    return RelationMarker(
        RelationType.MANY_TO_ONE,
        target,
        inverse_side,
        nullable=nullable,
        on_delete=on_delete,
        join_column=join_column or JoinColumn(),
        default=default,
    )


def ManyToMany(
    target: Target,
    inverse_side: str | None = None,
    *,
    join_table: JoinTable | bool = False,
    cascade: bool = False,
    default_factory: Callable[[], Any] = list,
) -> Any:
    """Owning side iff ``join_table`` is given (``True`` for defaults, or a :class:`JoinTable`
    for explicit naming) -- exactly one side of a many-to-many pair should own the join table."""
    resolved_join_table = JoinTable() if join_table is True else (join_table or None)
    return RelationMarker(
        RelationType.MANY_TO_MANY,
        target,
        inverse_side,
        cascade=cascade,
        join_table=resolved_join_table,
        default_factory=default_factory,
    )
