"""The one seam where ``sqlalchemy`` (Core, never the declarative/ORM layer) is used --
translates our own :mod:`~austial.orm.metadata` / :mod:`~austial.orm.expression` shapes into
SQLAlchemy Core ``Table``/``Column``/``Select``/... objects for dialect-aware SQL compilation,
async connection pooling, and DBAPI execution. Shared by ``driver/postgres.py`` and
``driver/sqlite.py`` -- nothing outside ``driver/`` imports this module or ``sqlalchemy`` itself.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from austial.orm.decorators.entity import get_entity_metadata
from austial.orm.expression import DeleteSpec, DriverResult, InsertSpec, SelectSpec, UpdateSpec, WhereFragment
from austial.orm.metadata import column_types as ct
from austial.orm.metadata.entity_metadata import ColumnMetadata, EntityMetadata, RelationMetadata
from austial.orm.naming_strategy import NamingStrategy

_TYPE_MAP: dict[type, Any] = {
    ct.String: lambda t: sa.String(length=t.length),
    ct.Text: lambda t: sa.Text(),
    ct.Integer: lambda t: sa.Integer(),
    ct.BigInteger: lambda t: sa.BigInteger(),
    ct.Boolean: lambda t: sa.Boolean(),
    ct.Float: lambda t: sa.Float(),
    ct.Numeric: lambda t: sa.Numeric(precision=t.precision, scale=t.scale),
    ct.DateTime: lambda t: sa.DateTime(timezone=t.timezone),
    ct.Date: lambda t: sa.Date(),
    ct.Time: lambda t: sa.Time(),
    ct.UUIDType: lambda t: sa.Uuid(),
    ct.JSONType: lambda t: sa.JSON(),
    ct.EnumType: lambda t: sa.Enum(*t.values) if t.values else sa.String(),
}


def sqla_type_for(column_type: ct.ColumnType) -> sa.types.TypeEngine:
    factory = _TYPE_MAP.get(type(column_type))
    if factory is None:  # pragma: no cover - defensive, every ColumnType subclass is mapped above
        return sa.String()
    return factory(column_type)


def _sqla_column(column: ColumnMetadata) -> sa.Column:
    return sa.Column(
        column.column_name,
        sqla_type_for(column.type_),
        primary_key=column.primary,
        autoincrement=column.generated and column.primary,
        nullable=column.nullable,
        unique=column.unique or None,
        index=column.index or None,
    )


class SchemaCatalog:
    """Builds and holds the ``sqlalchemy.Table`` objects for every entity a ``DataSource`` was
    given, plus any many-to-many join tables. Built once per ``DataSource``, reused for every
    query -- table construction (walking metadata, resolving relation targets) is not repeated
    per-request.

    Phase-1 limitation, called out explicitly: join resolution only supports single-level
    relation paths (``"<root_alias>.<relation_attr>"``), matching the eager-load design (no
    nested ``"a.b.c"`` paths yet) -- see ``QueryBuilder``/``EntityManager.FindOptions``.
    """

    def __init__(self, entities: Sequence[type], naming_strategy: NamingStrategy):
        self.naming_strategy = naming_strategy
        self.metadata_by_entity: dict[type, EntityMetadata] = {e: get_entity_metadata(e) for e in entities}
        self.sqla_metadata = sa.MetaData()
        self.tables: dict[type, sa.Table] = {}
        self.join_tables: dict[tuple[type, str], sa.Table] = {}
        self._build()

    def _build(self) -> None:
        # Pass 1: bare tables (columns only) so every target table exists before any relation
        # tries to reference it with a ForeignKey, regardless of entity declaration order.
        for entity, meta in self.metadata_by_entity.items():
            table = sa.Table(meta.table_name, self.sqla_metadata, *[_sqla_column(c) for c in meta.columns])
            self.tables[entity] = table

        # Pass 2: FK columns for owning relations, and many-to-many join tables.
        for entity, meta in self.metadata_by_entity.items():
            for rel in meta.relations:
                if not rel.owning:
                    continue
                if rel.join_column is not None:
                    self._add_fk_column(entity, meta, rel)
                elif rel.join_table is not None:
                    self._build_join_table(entity, meta, rel)

    def _add_fk_column(self, entity: type, meta: EntityMetadata, rel: RelationMetadata) -> None:
        target_meta = self.metadata_by_entity[rel.target()]
        target_table = self.tables[rel.target()]
        assert rel.join_column is not None
        referenced_col_name = self._resolve_referenced_column(target_meta, rel.join_column.referenced_column_name)
        fk_col_name = self.fk_column_name(rel)
        pk_col = target_table.c[referenced_col_name]
        self.tables[entity].append_column(
            sa.Column(fk_col_name, pk_col.type, sa.ForeignKey(pk_col, ondelete=rel.on_delete), nullable=rel.nullable)
        )

    def _build_join_table(self, entity: type, meta: EntityMetadata, rel: RelationMetadata) -> None:
        target_meta = self.metadata_by_entity[rel.target()]
        target_table = self.tables[rel.target()]
        own_pk = self.tables[entity].c[self.pk_column(meta).column_name]
        target_pk = target_table.c[self.pk_column(target_meta).column_name]

        jt = rel.join_table
        assert jt is not None
        table_name = jt.name or self.naming_strategy.join_table_name(meta.table_name, target_meta.table_name)
        own_col_name = jt.join_column_name or self.naming_strategy.join_table_column_name(meta.table_name, "id")
        target_col_name = jt.inverse_join_column_name or self.naming_strategy.join_table_column_name(
            target_meta.table_name, "id"
        )
        table = sa.Table(
            table_name,
            self.sqla_metadata,
            sa.Column(own_col_name, own_pk.type, sa.ForeignKey(own_pk), primary_key=True),
            sa.Column(target_col_name, target_pk.type, sa.ForeignKey(target_pk), primary_key=True),
        )
        self.join_tables[(entity, rel.attribute_name)] = table

    @staticmethod
    def pk_column(meta: EntityMetadata) -> ColumnMetadata:
        """Phase-1 limitation: only single-column primary keys are supported (composite keys
        are a later-phase concern)."""
        primaries = meta.primary_columns
        if len(primaries) != 1:
            from austial.orm.exceptions import MissingPrimaryKeyError

            raise MissingPrimaryKeyError(meta.entity_cls)
        return primaries[0]

    @classmethod
    def _resolve_referenced_column(cls, target_meta: EntityMetadata, referenced_column_name: str) -> str:
        # `referenced_column_name` on JoinColumn defaults to the attribute name "id"; resolve it
        # to the target's actual mapped/physical column name (they usually match, but needn't).
        col = target_meta.column(referenced_column_name)
        return col.column_name if col is not None else cls.pk_column(target_meta).column_name

    def fk_column_name(self, rel: RelationMetadata) -> str:
        if rel.join_column and rel.join_column.name:
            return rel.join_column.name
        referenced = rel.join_column.referenced_column_name if rel.join_column else "id"
        return self.naming_strategy.join_column_name(rel.attribute_name, referenced)

    def owning_relation_for(
        self, meta: EntityMetadata, rel: RelationMetadata
    ) -> tuple[EntityMetadata, RelationMetadata]:
        """Resolves the *owning* side's metadata/relation for a (possibly non-owning) relation --
        e.g. given ``Owner.cats`` (``OneToMany``, non-owning), returns ``Cat``'s metadata and its
        ``owner`` (``ManyToOne``, owning) relation, which is what actually carries the FK/join-table
        info needed to build a JOIN."""
        if rel.owning:
            return meta, rel
        if rel.inverse_side is None:  # pragma: no cover - guarded by DataSource validation
            raise ValueError(f"Relation {rel.attribute_name!r} has no inverse_side to resolve ownership from")
        target_meta = self.metadata_by_entity[rel.target()]
        owning_rel = target_meta.relation(rel.inverse_side)
        if owning_rel is None:  # pragma: no cover - guarded by DataSource validation
            raise ValueError(f"Inverse side {rel.inverse_side!r} not found on {rel.target().__name__!r}")
        return target_meta, owning_rel


def _combine_where(fragments: list[WhereFragment]) -> Any:
    clause: Any = None
    for frag in fragments:
        piece = sa.text(frag.sql).bindparams(**frag.params)
        if clause is None:
            clause = piece
        elif frag.connector == "OR":
            clause = sa.or_(clause, piece)
        else:
            clause = sa.and_(clause, piece)
    return clause


_AGGREGATE_FN: dict[str, Any] = {
    "SUM": sa.func.sum,
    "AVG": sa.func.avg,
    "MIN": sa.func.min,
    "MAX": sa.func.max,
}


def _compile_aggregate_select(spec: SelectSpec, root_table: Any) -> tuple[Any, dict[str, list[str]]]:
    """Compiles ``spec.aggregate`` (``SUM``/``AVG``/``MIN``/``MAX``, optionally grouped by
    ``spec.group_by``) instead of the normal "every mapped column" select list. No joins --
    matches ``EntityManager.count()``'s Phase-1 scope (WHERE, and here also GROUP BY, on the root
    entity's own columns only)."""
    agg = spec.aggregate
    assert agg is not None
    fn = _AGGREGATE_FN[agg.fn]
    group_cols = [root_table.c[name] for name in spec.group_by]
    columns: list[Any] = [*group_cols, fn(root_table.c[agg.column]).label(agg.result_alias)]

    stmt = sa.select(*columns).select_from(root_table)
    if spec.wheres:
        stmt = stmt.where(_combine_where(spec.wheres))
    if group_cols:
        stmt = stmt.group_by(*group_cols)
    return stmt, {spec.alias: []}


def compile_select(spec: SelectSpec, catalog: SchemaCatalog) -> tuple[Any, dict[str, list[str]]]:
    """Returns ``(select_statement, column_labels_by_alias)`` -- the latter tells
    ``hydration.py`` which result-column labels belong to which alias/entity."""
    root_meta = catalog.metadata_by_entity[spec.entity]
    root_table = catalog.tables[spec.entity].alias(spec.alias)

    if spec.aggregate is not None:
        return _compile_aggregate_select(spec, root_table)

    columns: list[Any] = []
    labels_by_alias: dict[str, list[str]] = {spec.alias: []}
    for col in root_meta.columns:
        label = f"{spec.alias}__{col.column_name}"
        columns.append(root_table.c[col.column_name].label(label))
        labels_by_alias[spec.alias].append(col.column_name)

    selectable: Any = root_table
    for join in spec.joins:
        _, relation_attr = join.relation_name.split(".", 1)
        rel = root_meta.relation(relation_attr)
        if rel is None:
            from austial.orm.exceptions import RelationNotFoundError

            raise RelationNotFoundError(spec.entity, relation_attr)

        target_meta = catalog.metadata_by_entity[rel.target()]
        target_table = catalog.tables[rel.target()].alias(join.alias)
        isouter = join.join_type == "LEFT"

        if rel.owning and rel.join_column is not None:
            fk_col_name = catalog.fk_column_name(rel)
            referenced_col_name = catalog._resolve_referenced_column(  # noqa: SLF001 - same module family
                target_meta, rel.join_column.referenced_column_name
            )
            condition = root_table.c[fk_col_name] == target_table.c[referenced_col_name]
            selectable = selectable.join(target_table, condition, isouter=isouter)
        elif (
            rel.join_table is None
            and (owning := catalog.owning_relation_for(root_meta, rel))[1].join_column is not None
        ):
            _, owning_rel = owning
            fk_col_name = catalog.fk_column_name(owning_rel)
            root_pk_name = catalog.pk_column(root_meta).column_name
            condition = root_table.c[root_pk_name] == target_table.c[fk_col_name]
            selectable = selectable.join(target_table, condition, isouter=isouter)
        else:
            # `or` can't be used here: a found `sa.Table` doesn't support `__bool__`, so a plain
            # `dict.get(...) or dict[...]` raises `TypeError` instead of short-circuiting.
            owning_side_table = catalog.join_tables.get((spec.entity, rel.attribute_name))
            join_table = (
                owning_side_table
                if owning_side_table is not None
                else catalog.join_tables[(rel.target(), rel.inverse_side or "")]
            )
            own_fk = next(
                c
                for c in join_table.columns
                if next(iter(c.foreign_keys)).column.table.name == catalog.tables[spec.entity].name
            )
            target_fk = next(
                c
                for c in join_table.columns
                if next(iter(c.foreign_keys)).column.table.name == catalog.tables[rel.target()].name
            )
            root_pk_name = catalog.pk_column(root_meta).column_name
            target_pk_name = catalog.pk_column(target_meta).column_name
            selectable = selectable.join(join_table, root_table.c[root_pk_name] == own_fk, isouter=isouter)
            selectable = selectable.join(
                target_table, join_table.c[target_fk.name] == target_table.c[target_pk_name], isouter=isouter
            )

        if join.select:
            labels_by_alias[join.alias] = []
            for col in target_meta.columns:
                label = f"{join.alias}__{col.column_name}"
                columns.append(target_table.c[col.column_name].label(label))
                labels_by_alias[join.alias].append(col.column_name)

    stmt = sa.select(*columns).select_from(selectable)
    if spec.wheres:
        stmt = stmt.where(_combine_where(spec.wheres))
    for ob in spec.order_by:
        stmt = stmt.order_by(sa.text(f"{ob.column} {ob.direction}"))
    if spec.limit is not None:
        stmt = stmt.limit(spec.limit)
    if spec.offset is not None:
        stmt = stmt.offset(spec.offset)
    return stmt, labels_by_alias


def compile_insert(spec: InsertSpec, catalog: SchemaCatalog) -> Any:
    meta = catalog.metadata_by_entity[spec.entity]
    table = catalog.tables[spec.entity]
    pk_cols = [table.c[c.column_name] for c in meta.primary_columns]
    stmt = sa.insert(table).values(**spec.values)
    if pk_cols:
        stmt = stmt.returning(*pk_cols)
    return stmt


def compile_update(spec: UpdateSpec, catalog: SchemaCatalog) -> Any:
    table = catalog.tables[spec.entity]
    stmt = sa.update(table).values(**spec.values)
    if spec.wheres:
        stmt = stmt.where(_combine_where(spec.wheres))
    return stmt


def compile_delete(spec: DeleteSpec, catalog: SchemaCatalog) -> Any:
    table = catalog.tables[spec.entity]
    stmt = sa.delete(table)
    if spec.wheres:
        stmt = stmt.where(_combine_where(spec.wheres))
    return stmt


def rows_to_result(rows: Sequence[Any]) -> DriverResult:
    return DriverResult(rows=[dict(row._mapping) for row in rows], row_count=len(rows))  # noqa: SLF001 - sqlalchemy Row API
