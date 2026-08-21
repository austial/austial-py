"""Entity metadata dataclasses -- the resolved, framework-internal description of an
``@Entity()``-decorated class, built once by ``decorators/entity.py`` and stored in
:class:`~austial.orm.metadata.registry.MetadataRegistry`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from austial.orm.metadata.column_types import ColumnType


class RelationType(StrEnum):
    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_MANY = "ONE_TO_MANY"
    MANY_TO_ONE = "MANY_TO_ONE"
    MANY_TO_MANY = "MANY_TO_MANY"


@dataclass
class ColumnMetadata:
    attribute_name: str
    column_name: str
    type_: ColumnType
    python_type: Any
    primary: bool = False
    generated: bool = False
    nullable: bool = False
    unique: bool = False
    index: bool = False
    default: Any = None
    create_date: bool = False
    update_date: bool = False


@dataclass
class JoinColumnMetadata:
    name: str | None = None
    referenced_column_name: str = "id"


@dataclass
class JoinTableMetadata:
    name: str | None = None
    join_column_name: str | None = None
    inverse_join_column_name: str | None = None


@dataclass
class RelationMetadata:
    attribute_name: str
    relation_type: RelationType
    target_resolver: Callable[[], type]
    inverse_side: str | None = None
    nullable: bool = True
    on_delete: str | None = None
    cascade: bool = False
    join_column: JoinColumnMetadata | None = None
    join_table: JoinTableMetadata | None = None

    # Resolved lazily by DataSource.__init__ once every entity in `entities=[...]` has been
    # imported/decorated -- see DataSource._resolve_relations().
    _resolved_target: type | None = field(default=None, repr=False)

    @property
    def owning(self) -> bool:
        if self.relation_type is RelationType.MANY_TO_ONE:
            return True
        if self.relation_type is RelationType.ONE_TO_MANY:
            return False
        if self.relation_type is RelationType.ONE_TO_ONE:
            return self.join_column is not None
        if self.relation_type is RelationType.MANY_TO_MANY:
            return self.join_table is not None
        return False  # pragma: no cover - exhaustive above

    def target(self) -> type:
        if self._resolved_target is None:
            self._resolved_target = self.target_resolver()
        return self._resolved_target


@dataclass
class EntityMetadata:
    entity_cls: type
    table_name: str
    columns: list[ColumnMetadata] = field(default_factory=list)
    relations: list[RelationMetadata] = field(default_factory=list)
    append_only: bool = False

    @property
    def primary_columns(self) -> list[ColumnMetadata]:
        return [c for c in self.columns if c.primary]

    def column(self, attribute_name: str) -> ColumnMetadata | None:
        return next((c for c in self.columns if c.attribute_name == attribute_name), None)

    def relation(self, attribute_name: str) -> RelationMetadata | None:
        return next((r for r in self.relations if r.attribute_name == attribute_name), None)
