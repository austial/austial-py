"""``EntityManager`` -- mirrors TypeORM's ``EntityManager``: the low-level, entity-type-agnostic
API every :class:`~austial.orm.repository.Repository` delegates to. One ``EntityManager`` per
``DataSource`` (or per transaction -- see ``DataSource.transaction()``), bound to one
``Driver``/``SchemaCatalog`` pair.

No unit-of-work, no dirty-checking, no lazy-loading proxies (Phase-1 design decision, matches
TypeORM's data-mapper mode rather than Active Record): ``save()`` always issues either a full
INSERT (primary key unset) or a full-column UPDATE (primary key set); relations are only ever
populated when eagerly requested via ``FindOptions.relations``.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import count
from typing import Any, Literal, TypeVar, overload

from austial.orm.decorators.entity import get_entity_metadata
from austial.orm.driver.base import Driver
from austial.orm.driver.sqlalchemy_support import SchemaCatalog
from austial.orm.exceptions import AppendOnlyViolationError, OrmError, RelationNotFoundError
from austial.orm.expression import (
    AggregateFn,
    Connector,
    DeleteSpec,
    In,
    InsertSpec,
    IsNull,
    NotIn,
    NotNull,
    TypedParam,
    UpdateSpec,
    WhereFragment,
)
from austial.orm.identifier import quote_ref
from austial.orm.metadata.column_types import EnumType, enum_type_name
from austial.orm.metadata.entity_metadata import ColumnMetadata, EntityMetadata, RelationType
from austial.orm.query_builder import QueryBuilder

T = TypeVar("T")

Criteria = dict[str, Any] | int | str
WhereClause = dict[str, Any] | list[dict[str, Any]]


@dataclass
class FindOptions:
    where: WhereClause | None = None
    relations: Sequence[str] | None = None
    order_by: list[tuple[str, Literal["ASC", "DESC"]]] | None = None  # [(attribute_name, direction), ...]
    skip: int | None = None
    take: int | None = None


@dataclass
class UpdateResult:
    affected: int


@dataclass
class DeleteResult:
    affected: int


def _typed_value(meta: EntityMetadata, column: ColumnMetadata, value: Any) -> Any:
    """Wraps ``value`` as a :class:`TypedParam` when ``column`` is a native ``ENUM`` -- lets the
    driver bind it with the real Postgres enum type instead of an untyped parameter (asyncpg
    otherwise rejects comparing an enum column to an untyped string). No-op for every other
    column type, and for the SQLite driver used in tests (which ignores ``TypedParam.column_type``
    beyond the plain value)."""
    if isinstance(column.type_, EnumType):
        return TypedParam(value, column.type_, enum_type_name(meta.table_name, column.column_name))
    return value


def _build_where_fragments(meta: EntityMetadata, alias: str, where: WhereClause | None) -> list[WhereFragment]:
    """Translates a ``FindOptions.where``-shaped value into raw-SQL ``WhereFragment``s -- a
    ``dict`` is one AND-of-equality group, a ``list[dict]`` is OR-of-AND-groups (matches
    TypeORM's ``FindOptionsWhere`` semantics). A value wrapped in :class:`In`/:class:`NotIn`
    (mirrors TypeORM's ``In()``) compiles to ``column IN (...)``/``NOT IN (...)`` instead of
    equality. Values only ever travel through ``params``, never string-formatted into ``sql`` --
    same SQL-injection-safety guarantee as ``QueryBuilder``."""
    if not where:
        return []
    groups = where if isinstance(where, list) else [where]
    fragments: list[WhereFragment] = []
    counter = count()
    for group_index, group in enumerate(groups):
        clauses: list[str] = []
        params: dict[str, Any] = {}
        for attr_name, value in group.items():
            column = meta.column(attr_name)
            if column is None:
                raise OrmError(f"{meta.entity_cls.__name__!r} has no column {attr_name!r}")
            qualified = quote_ref(alias, column.column_name)
            if isinstance(value, (IsNull, NotNull)):
                clauses.append(f"{qualified} IS {'NOT ' if isinstance(value, NotNull) else ''}NULL")
            elif isinstance(value, (In, NotIn)):
                membership_values = list(value.values)
                negate = isinstance(value, NotIn)
                if not membership_values:
                    clauses.append("1 = 1" if negate else "1 = 0")
                    continue
                names = [f"p{next(counter)}" for _ in membership_values]
                placeholders = ", ".join(f":{n}" for n in names)
                op = "NOT IN" if negate else "IN"
                clauses.append(f"{qualified} {op} ({placeholders})")
                for param_name, item in zip(names, membership_values, strict=True):
                    params[param_name] = _typed_value(meta, column, item)
            else:
                param_name = f"p{next(counter)}"
                clauses.append(f"{qualified} = :{param_name}")
                params[param_name] = _typed_value(meta, column, value)
        connector: Connector = "AND" if group_index == 0 else "OR"
        fragments.append(WhereFragment(" AND ".join(clauses), params, connector))
    return fragments


def _criteria_where(meta: EntityMetadata, alias: str, criteria: Criteria) -> list[WhereFragment]:
    """``criteria`` is either a ``dict`` (same shape as ``FindOptions.where``'s AND-group) or a
    bare scalar primary-key value -- the common ``update(Cat, 1, {...})``/``delete(Cat, 1)``
    shorthand TypeORM's ``Repository.update()``/``.delete()`` also accept."""
    if isinstance(criteria, dict):
        return _build_where_fragments(meta, alias, criteria)
    pk = SchemaCatalog.pk_column(meta)
    return [WhereFragment(f"{quote_ref(alias, pk.column_name)} = :pk", {"pk": criteria}, "AND")]


def _as_list(entity_instance: T | Sequence[T]) -> list[T]:
    if isinstance(entity_instance, Sequence) and not isinstance(entity_instance, (str, bytes)):
        return list(entity_instance)
    return [entity_instance]


class EntityManager:
    def __init__(self, driver: Driver, catalog: SchemaCatalog):
        self._driver = driver
        self._catalog = catalog

    def create_query_builder(self, entity: type[T], alias: str) -> QueryBuilder[T]:
        return QueryBuilder(entity, alias, self._driver, self._catalog)

    @staticmethod
    def _alias_for(meta: EntityMetadata) -> str:
        # Reused as the qualifier for UPDATE/DELETE WHERE clauses too -- `compile_update`/
        # `compile_delete` never alias the table, and Postgres/SQLite both accept the table's own
        # name as its implicit correlation name in an UPDATE/DELETE's WHERE, so one alias choice
        # (the table name) works for every statement kind EntityManager issues.
        return meta.table_name

    @staticmethod
    def _apply_wheres(qb: QueryBuilder[Any], wheres: list[WhereFragment]) -> None:
        for i, frag in enumerate(wheres):
            if i == 0:
                qb.where(frag.sql, frag.params)
            elif frag.connector == "OR":
                qb.or_where(frag.sql, frag.params)
            else:
                qb.and_where(frag.sql, frag.params)

    def _apply_options(
        self, qb: QueryBuilder[Any], meta: EntityMetadata, alias: str, options: FindOptions | None
    ) -> None:
        if options is None:
            return
        self._apply_wheres(qb, _build_where_fragments(meta, alias, options.where))
        for relation_attr in options.relations or ():
            if meta.relation(relation_attr) is None:
                raise RelationNotFoundError(meta.entity_cls, relation_attr)
            qb.left_join_and_select(f"{alias}.{relation_attr}", relation_attr)
        for attr_name, direction in options.order_by or ():
            column = meta.column(attr_name)
            physical = column.column_name if column is not None else attr_name
            qb.add_order_by(quote_ref(alias, physical), direction)
        if options.take is not None:
            qb.take(options.take)
        if options.skip is not None:
            qb.skip(options.skip)

    async def find(self, entity: type[T], options: FindOptions | None = None) -> list[T]:
        meta = get_entity_metadata(entity)
        alias = self._alias_for(meta)
        qb = self.create_query_builder(entity, alias)
        self._apply_options(qb, meta, alias, options)
        return await qb.get_many()

    async def find_one(self, entity: type[T], options: FindOptions) -> T | None:
        meta = get_entity_metadata(entity)
        alias = self._alias_for(meta)
        qb = self.create_query_builder(entity, alias)
        self._apply_options(qb, meta, alias, options)
        return await qb.get_one()

    async def find_by(self, entity: type[T], criteria: dict[str, Any]) -> list[T]:
        return await self.find(entity, FindOptions(where=criteria))

    async def find_one_by(self, entity: type[T], criteria: dict[str, Any]) -> T | None:
        return await self.find_one(entity, FindOptions(where=criteria))

    async def count(self, entity: type[T], options: FindOptions | None = None) -> int:
        # Deliberately ignores `options.relations`/`order_by`/paging -- joining eager-loaded
        # to-many relations here would fan out rows and corrupt the count; only WHERE applies.
        meta = get_entity_metadata(entity)
        alias = self._alias_for(meta)
        qb = self.create_query_builder(entity, alias)
        self._apply_wheres(qb, _build_where_fragments(meta, alias, options.where if options else None))
        rows = await qb.get_raw_many()
        return len(rows)

    @overload
    async def aggregate(
        self,
        entity: type[T],
        fn: AggregateFn,
        column: str,
        *,
        criteria: dict[str, Any] | None = None,
        group_by: None = None,
    ) -> float: ...

    @overload
    async def aggregate(
        self,
        entity: type[T],
        fn: AggregateFn,
        column: str,
        *,
        criteria: dict[str, Any] | None = None,
        group_by: Sequence[str],
    ) -> list[dict[str, Any]]: ...

    async def aggregate(
        self,
        entity: type[T],
        fn: AggregateFn,
        column: str,
        *,
        criteria: dict[str, Any] | None = None,
        group_by: Sequence[str] | None = None,
    ) -> float | list[dict[str, Any]]:
        """Runs ``SUM``/``AVG``/``MIN``/``MAX`` over ``column`` (an attribute name, translated to
        its physical column the same way ``criteria``'s keys are) across rows matching
        ``criteria`` (same AND/OR shape as ``find_by``'s criteria dict). Deliberately mirrors
        ``count()``'s scope: WHERE (+ here, optionally GROUP BY) only, no joins/paging.

        Without ``group_by``: returns a single scalar. SQL's aggregate of zero matching rows is
        ``NULL``; normalized to ``0.0`` here so callers don't have to special-case ``None``.

        With ``group_by`` (attribute names, same translation as ``column``): returns one ``dict``
        per group actually present in the data -- the group-by attribute names as keys, plus
        ``"value"`` holding the aggregate result. Groups with no matching rows don't appear
        (standard SQL ``GROUP BY`` semantics), same as e.g. currency-breakdown reporting expects.
        """
        meta = get_entity_metadata(entity)
        alias = self._alias_for(meta)
        agg_column = meta.column(column)
        if agg_column is None:
            raise OrmError(f"{entity.__name__!r} has no column {column!r}")

        group_columns: list[str] = []
        for attr_name in group_by or ():
            group_column = meta.column(attr_name)
            if group_column is None:
                raise OrmError(f"{entity.__name__!r} has no column {attr_name!r}")
            group_columns.append(group_column.column_name)

        qb = self.create_query_builder(entity, alias)
        self._apply_wheres(qb, _build_where_fragments(meta, alias, criteria))
        if group_columns:
            qb.group_by(*group_columns)
        rows = await qb.get_aggregate_raw(fn, agg_column.column_name)

        if not group_by:
            value = rows[0]["value"] if rows else None
            return float(value) if value is not None else 0.0
        return rows

    @overload
    async def sum(
        self, entity: type[T], column: str, *, criteria: dict[str, Any] | None = None, group_by: None = None
    ) -> float: ...

    @overload
    async def sum(
        self, entity: type[T], column: str, *, criteria: dict[str, Any] | None = None, group_by: Sequence[str]
    ) -> list[dict[str, Any]]: ...

    async def sum(
        self,
        entity: type[T],
        column: str,
        *,
        criteria: dict[str, Any] | None = None,
        group_by: Sequence[str] | None = None,
    ) -> float | list[dict[str, Any]]:
        """Convenience for ``aggregate(entity, "SUM", column, ...)`` -- the common case (e.g.
        total AUM across matching holdings)."""
        return await self.aggregate(entity, "SUM", column, criteria=criteria, group_by=group_by)

    @overload
    async def save(self, entity_instance: Sequence[T]) -> list[T]: ...

    @overload
    async def save(self, entity_instance: T) -> T: ...

    async def save(self, entity_instance: Any) -> Any:
        instances = _as_list(entity_instance)
        saved = [await self._save_one(instance) for instance in instances]
        is_sequence = isinstance(entity_instance, Sequence) and not isinstance(entity_instance, (str, bytes))
        return saved if is_sequence else saved[0]

    @overload
    async def insert(self, entity_instance: Sequence[T]) -> list[T]: ...

    @overload
    async def insert(self, entity_instance: T) -> T: ...

    async def insert(self, entity_instance: Any) -> Any:
        """INSERT only -- never an UPDATE, whatever the primary key holds.

        ``save()`` decides between INSERT and UPDATE from the primary key (unset -> insert), which
        makes an entity with an *application-assigned* key (UUIDs, natural keys) impossible to
        insert: ``save()`` sees the key and issues an UPDATE that matches nothing. ``insert()`` is the
        explicit path for that case, and the only write an ``append_only`` entity with a pre-set key
        will accept. A duplicate primary key raises the driver's integrity error.
        """
        instances = _as_list(entity_instance)
        inserted = [await self._insert_one(instance) for instance in instances]
        is_sequence = isinstance(entity_instance, Sequence) and not isinstance(entity_instance, (str, bytes))
        return inserted if is_sequence else inserted[0]

    async def _insert_one(self, instance: T) -> T:
        meta = get_entity_metadata(type(instance))
        now = datetime.datetime.now(datetime.UTC)
        for column in meta.columns:
            if column.update_date or column.create_date:
                setattr(instance, column.attribute_name, now)
        insert_columns = [c for c in meta.columns if not (c.generated and c.primary)]
        values = {c.column_name: getattr(instance, c.attribute_name) for c in insert_columns}
        values.update(self._owning_relation_values(meta, instance))
        result = await self._driver.execute_insert(InsertSpec(entity=type(instance), values=values))
        if result.rows:
            row = result.rows[0]
            for c in meta.primary_columns:
                if c.column_name in row:
                    setattr(instance, c.attribute_name, row[c.column_name])
        return instance

    def _owning_relation_values(self, meta: EntityMetadata, instance: Any) -> dict[str, Any]:
        """Physical FK-column values for this instance's owning single-valued relations
        (``ManyToOne``, ``OneToOne`` w/ ``join_column``) -- these columns live only in
        ``SchemaCatalog`` (built from relation metadata), never in ``EntityMetadata.columns``, so
        ``save()`` must compute them separately from the plain-column values above.

        ``ManyToMany`` (join-table) relations are deliberately excluded: Phase-1 has no
        unit-of-work/cascade, so join-table rows are never written by ``save()`` -- populate them
        directly (e.g. via ``Driver.execute_raw()``) until a later phase adds relation cascades.
        """
        values: dict[str, Any] = {}
        for rel in meta.relations:
            if (
                not rel.owning
                or rel.join_column is None
                or rel.relation_type
                not in (
                    RelationType.MANY_TO_ONE,
                    RelationType.ONE_TO_ONE,
                )
            ):
                continue
            related = getattr(instance, rel.attribute_name)
            fk_column_name = self._catalog.fk_column_name(rel)
            if related is None:
                values[fk_column_name] = None
                continue
            target_meta = get_entity_metadata(type(related))
            target_pk = SchemaCatalog.pk_column(target_meta)
            values[fk_column_name] = getattr(related, target_pk.attribute_name)
        return values

    async def _save_one(self, instance: T) -> T:
        meta = get_entity_metadata(type(instance))
        pk = SchemaCatalog.pk_column(meta)
        is_insert = getattr(instance, pk.attribute_name) is None
        now = datetime.datetime.now(datetime.UTC)
        for column in meta.columns:
            if column.update_date or column.create_date and is_insert:
                setattr(instance, column.attribute_name, now)

        if is_insert:
            insert_columns = [c for c in meta.columns if not (c.generated and c.primary)]
            values = {c.column_name: getattr(instance, c.attribute_name) for c in insert_columns}
            values.update(self._owning_relation_values(meta, instance))
            result = await self._driver.execute_insert(InsertSpec(entity=type(instance), values=values))
            if result.rows:
                row = result.rows[0]
                for c in meta.primary_columns:
                    if c.column_name in row:
                        setattr(instance, c.attribute_name, row[c.column_name])
            return instance

        # Full-column UPDATE, excluding primary keys (identity, never rewritten) and
        # CreateDateColumn-marked columns (stamped once at insert time, immutable thereafter).
        if meta.append_only:
            raise AppendOnlyViolationError(meta.entity_cls, "save() on an already-persisted instance (UPDATE)")
        update_columns = [c for c in meta.columns if not c.primary and not c.create_date]
        values = {c.column_name: getattr(instance, c.attribute_name) for c in update_columns}
        values.update(self._owning_relation_values(meta, instance))
        alias = self._alias_for(meta)
        pk_value = getattr(instance, pk.attribute_name)
        where = [WhereFragment(f"{quote_ref(alias, pk.column_name)} = :pk", {"pk": pk_value}, "AND")]
        await self._driver.execute_update(UpdateSpec(entity=type(instance), values=values, wheres=where))
        return instance

    async def remove(self, entity_instance: T | Sequence[T]) -> None:
        for instance in _as_list(entity_instance):
            meta = get_entity_metadata(type(instance))
            if meta.append_only:
                raise AppendOnlyViolationError(meta.entity_cls, "remove()")
            pk = SchemaCatalog.pk_column(meta)
            alias = self._alias_for(meta)
            pk_value = getattr(instance, pk.attribute_name)
            where = [WhereFragment(f"{quote_ref(alias, pk.column_name)} = :pk", {"pk": pk_value}, "AND")]
            await self._driver.execute_delete(DeleteSpec(entity=type(instance), wheres=where))

    async def update(self, entity: type[T], criteria: Criteria, partial: dict[str, Any]) -> UpdateResult:
        """Bulk update -- issues a single ``UPDATE ... WHERE`` without loading matching rows
        first (matches TypeORM's ``Repository.update()``, distinct from ``save()``)."""
        meta = get_entity_metadata(entity)
        if meta.append_only:
            raise AppendOnlyViolationError(meta.entity_cls, "update()")
        alias = self._alias_for(meta)
        values: dict[str, Any] = {}
        for attr_name, value in partial.items():
            column = meta.column(attr_name)
            if column is None:
                raise OrmError(f"{entity.__name__!r} has no column {attr_name!r}")
            values[column.column_name] = value
        for column in meta.columns:
            if column.update_date and column.column_name not in values:
                values[column.column_name] = datetime.datetime.now(datetime.UTC)
        wheres = _criteria_where(meta, alias, criteria)
        affected = await self._driver.execute_update(UpdateSpec(entity=entity, values=values, wheres=wheres))
        return UpdateResult(affected=affected)

    async def delete(self, entity: type[T], criteria: Criteria) -> DeleteResult:
        """Bulk delete -- issues a single ``DELETE ... WHERE`` without loading matching rows
        first (matches TypeORM's ``Repository.delete()``, distinct from ``remove()``)."""
        meta = get_entity_metadata(entity)
        if meta.append_only:
            raise AppendOnlyViolationError(meta.entity_cls, "delete()")
        alias = self._alias_for(meta)
        wheres = _criteria_where(meta, alias, criteria)
        affected = await self._driver.execute_delete(DeleteSpec(entity=entity, wheres=wheres))
        return DeleteResult(affected=affected)
