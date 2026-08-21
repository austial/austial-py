"""``@Entity()`` -- mirrors TypeORM's ``@Entity()`` class decorator.

Reads back the ``ColumnMarker``/``RelationMarker`` default values declared via ``Column()``,
``PrimaryGeneratedColumn()``, ``ManyToOne()``, etc. (see ``decorators/column.py``/``relations.py``),
builds an :class:`~austial.orm.metadata.entity_metadata.EntityMetadata`, registers it in
:class:`~austial.orm.metadata.registry.MetadataRegistry` *and* on the class itself via the
framework's own ``set_metadata`` mechanism, and turns the class into a plain ``@dataclass`` so
instances behave like ordinary mutable Python objects (``Cat(name="Tom")``, attribute access/
assignment, ``repr``/``eq``) -- no active-record magic, no lazy proxies, no dirty-checking.
"""

from __future__ import annotations

import dataclasses
import sys
import typing
from collections.abc import Callable
from typing import Any, TypeVar

from austial.core.metadata import set_metadata
from austial.orm.decorators.column import (
    Column,
    ColumnMarker,
    CreateDateColumn,
    PrimaryColumn,
    PrimaryGeneratedColumn,
    UpdateDateColumn,
)
from austial.orm.decorators.relations import ManyToMany, ManyToOne, OneToMany, OneToOne, RelationMarker, target_resolver
from austial.orm.metadata.column_types import infer_column_type
from austial.orm.metadata.entity_metadata import ColumnMetadata, EntityMetadata, RelationMetadata
from austial.orm.metadata.registry import MetadataRegistry
from austial.orm.naming_strategy import DefaultNamingStrategy, NamingStrategy

ENTITY_METADATA = "austial:orm:entity"

T = TypeVar("T")

_default_naming_strategy = DefaultNamingStrategy()


def _resolve_annotations(cls: type) -> dict[str, Any]:
    """Best-effort, per-attribute annotation resolution -- unlike ``typing.get_type_hints(cls)``,
    one unresolvable forward reference doesn't abort resolution of every other attribute.

    This matters because a relation's target is routinely a sibling entity declared *later* in
    the same module (``Owner.cats: list["Cat"] = OneToMany(lambda: Cat, ...)``, with ``Cat``
    defined afterwards -- exactly the pattern this framework's own docs use). ``RelationMarker``
    already carries its target as a lazy callable (see ``decorators/relations.py``'s
    ``target_resolver``), never the annotation, so a still-unresolved forward reference on a
    relation attribute is harmless -- only ``Column()``-marked attributes actually consume the
    resolved type (to infer a ``ColumnType`` when none is given explicitly), and those are always
    already-defined types (``str``, ``int``, ``datetime.datetime``, ...), never forward refs.
    """
    module_globals = vars(sys.modules[cls.__module__])
    class_locals = dict(vars(cls))
    resolved: dict[str, Any] = {}
    for attr_name, raw in getattr(cls, "__annotations__", {}).items():
        forward = typing.ForwardRef(raw) if isinstance(raw, str) else raw
        try:
            resolved[attr_name] = typing._eval_type(forward, module_globals, class_locals)  # type: ignore[attr-defined]
        except NameError:
            resolved[attr_name] = raw
    return resolved


@typing.dataclass_transform(
    field_specifiers=(
        Column,
        PrimaryColumn,
        PrimaryGeneratedColumn,
        CreateDateColumn,
        UpdateDateColumn,
        OneToOne,
        OneToMany,
        ManyToOne,
        ManyToMany,
        ColumnMarker,
        RelationMarker,
    ),
)
def Entity(
    name: str | None = None,
    *,
    naming_strategy: NamingStrategy | None = None,
    append_only: bool = False,
) -> Callable[[type[T]], type[T]]:
    """Class decorator. Usable as ``@Entity()``, ``@Entity("custom_table_name")``, or
    ``@Entity(append_only=True)`` (composes with the positional ``name``, e.g.
    ``@Entity("ledger_entry", append_only=True)``).

    ``naming_strategy`` only affects *this* entity's default table/column names when the app's
    ``DataSource`` doesn't otherwise override them; the vast majority of callers never need it.

    ``append_only=True`` marks the entity as insert-only: ``EntityManager`` (and therefore every
    ``Repository`` method that funnels through it) rejects UPDATE/remove/delete against it,
    raising :class:`~austial.orm.exceptions.AppendOnlyViolationError` -- see that class's
    docstring for what this guard does and does not cover.
    """
    strategy = naming_strategy or _default_naming_strategy

    def decorator(cls: type[T]) -> type[T]:
        hints = _resolve_annotations(cls)
        columns: list[ColumnMetadata] = []
        relations: list[RelationMetadata] = []
        dataclass_fields: dict[str, Any] = {}

        for attr_name, python_type in hints.items():
            if attr_name.startswith("_"):
                continue
            marker = cls.__dict__.get(attr_name)

            if isinstance(marker, ColumnMarker):
                column_type = marker.type_ or infer_column_type(python_type)
                columns.append(
                    ColumnMetadata(
                        attribute_name=attr_name,
                        column_name=strategy.column_name(attr_name, marker.column_name),
                        type_=column_type,
                        python_type=python_type,
                        primary=marker.primary,
                        generated=marker.generated,
                        nullable=marker.nullable,
                        unique=marker.unique,
                        index=marker.index,
                        default=marker.default,
                        create_date=marker.create_date,
                        update_date=marker.update_date,
                    )
                )
                dataclass_fields[attr_name] = dataclasses.field(default=marker.default)

            elif isinstance(marker, RelationMarker):
                is_to_many = marker.relation_type.name in ("ONE_TO_MANY", "MANY_TO_MANY")
                relations.append(
                    RelationMetadata(
                        attribute_name=attr_name,
                        relation_type=marker.relation_type,
                        target_resolver=target_resolver(marker.target),
                        inverse_side=marker.inverse_side,
                        nullable=marker.nullable,
                        on_delete=marker.on_delete,
                        cascade=marker.cascade,
                        join_column=marker.join_column.to_metadata() if marker.join_column else None,
                        join_table=marker.join_table.to_metadata() if marker.join_table else None,
                    )
                )
                dataclass_fields[attr_name] = (
                    dataclasses.field(default_factory=marker.default_factory or list)
                    if is_to_many
                    else dataclasses.field(default=marker.default)
                )
            elif attr_name not in dataclass_fields:
                # A plain, un-marked annotated attribute -- not part of the mapped/persisted
                # schema (matches TypeORM: only decorated properties are columns/relations), but
                # still needs *some* default so it can never violate dataclass field-ordering
                # ("non-default argument follows default argument") relative to the mapped
                # fields above it, since every mapped field always carries an explicit default.
                existing = cls.__dict__.get(attr_name, None)
                dataclass_fields[attr_name] = existing if existing is not None else dataclasses.field(default=None)

        for attr_name, field_spec in dataclass_fields.items():
            setattr(cls, attr_name, field_spec)

        entity_cls = dataclasses.dataclass(eq=False, repr=True)(cls)

        table_name = strategy.table_name(entity_cls.__name__, name)
        metadata = EntityMetadata(
            entity_cls=entity_cls,
            table_name=table_name,
            columns=columns,
            relations=relations,
            append_only=append_only,
        )

        set_metadata(ENTITY_METADATA, metadata)(entity_cls)
        MetadataRegistry.register(entity_cls, metadata)
        return entity_cls

    return decorator


def get_entity_metadata(entity_cls: type) -> EntityMetadata:
    from austial.orm.exceptions import OrmError

    metadata = MetadataRegistry.get(entity_cls)
    if metadata is None:
        raise OrmError(f"{entity_cls!r} is not decorated with @Entity()")
    return metadata
