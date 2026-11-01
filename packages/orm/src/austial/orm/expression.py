"""SQL-free AST -- what :class:`~austial.orm.query_builder.QueryBuilder`/
:class:`~austial.orm.entity_manager.EntityManager` build up, and what a
:class:`~austial.orm.driver.base.Driver` compiles into real SQL.

Nothing in this module imports ``sqlalchemy``. This is the seam a future, fully-custom
(non-SQLAlchemy) driver would translate instead -- ``QueryBuilder``/``EntityManager``/
``Repository``/``DataSource`` never change regardless of what's on the other side of ``Driver``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from austial.orm.metadata.column_types import ColumnType

JoinType = Literal["INNER", "LEFT"]
OrderDirection = Literal["ASC", "DESC"]
Connector = Literal["AND", "OR"]
AggregateFn = Literal["SUM", "AVG", "MIN", "MAX"]


@dataclass
class TypedParam:
    """A bind value paired with its logical column type -- lets a driver bind it with real type
    information instead of an untyped DBAPI parameter (needed e.g. for Postgres native ``ENUM``
    columns via asyncpg, which reject an untyped string parameter against an enum operator).
    Only ``driver/sqlalchemy_support.py`` interprets this; a ``WhereFragment.params`` value that
    isn't a ``TypedParam`` is bound as-is."""

    value: Any
    column_type: ColumnType
    enum_name: str | None = None


@dataclass
class In:
    """Marks a ``FindOptions.where`` value as a membership test (mirrors TypeORM's ``In()``) --
    ``{"status": In([...])}`` compiles to ``status IN (...)`` instead of equality."""

    values: Sequence[Any]


@dataclass
class NotIn:
    """The negated counterpart of :class:`In` -- compiles to ``status NOT IN (...)``."""

    values: Sequence[Any]


@dataclass
class IsNull:
    """Marks a ``FindOptions.where`` value as ``column IS NULL`` (mirrors TypeORM's ``IsNull()``) -- a plain
    ``None`` compiles to ``column = NULL``, which never matches, so this is the way to filter or atomically
    claim rows whose nullable column is still unset (``update({"used_at": IsNull()}, {...})``)."""


@dataclass
class NotNull:
    """The negated counterpart of :class:`IsNull` -- compiles to ``column IS NOT NULL``."""


@dataclass
class WhereFragment:
    """A raw SQL boolean expression plus its *separately* bound parameters -- e.g.
    ``WhereFragment("cat.name = :name", {"name": "Tom"})``. Values are never string-formatted
    into ``sql``; the driver hands ``params`` to the DBAPI as real bind parameters. This is the
    only mechanism by which ``.where()``/``.and_where()``/``.or_where()`` accept conditions, and
    it's what makes them SQL-injection-safe by construction."""

    sql: str
    params: dict[str, Any] = field(default_factory=dict)
    connector: Connector = "AND"


@dataclass
class JoinSpec:
    relation_name: str  # dotted, e.g. "cat.owner"
    alias: str
    join_type: JoinType = "LEFT"
    select: bool = True  # False for `.inner_join()` (join without adding columns to the result)


@dataclass
class OrderBySpec:
    column: str
    direction: OrderDirection = "ASC"


@dataclass
class AggregateSpec:
    """A single ``SUM``/``AVG``/``MIN``/``MAX`` applied to one physical column -- attached to a
    ``SelectSpec`` in place of its normal "every mapped column" select list. Mirrors
    ``EntityManager.count()``'s Phase-1 scope: no joins, WHERE (+ optional ``SelectSpec.group_by``)
    only."""

    fn: AggregateFn
    column: str  # physical column name on the root entity/alias
    result_alias: str = "value"


@dataclass
class SelectSpec:
    entity: type
    alias: str
    columns: list[str] | None = None  # None = all mapped columns
    wheres: list[WhereFragment] = field(default_factory=list)
    joins: list[JoinSpec] = field(default_factory=list)
    order_by: list[OrderBySpec] = field(default_factory=list)
    limit: int | None = None
    offset: int | None = None
    aggregate: AggregateSpec | None = None
    group_by: list[str] = field(default_factory=list)  # physical column names on the root entity/alias


@dataclass
class InsertSpec:
    entity: type
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class UpdateSpec:
    entity: type
    values: dict[str, Any] = field(default_factory=dict)
    wheres: list[WhereFragment] = field(default_factory=list)


@dataclass
class DeleteSpec:
    entity: type
    wheres: list[WhereFragment] = field(default_factory=list)


@dataclass
class DriverResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    # Only populated by `execute_select` for queries with joins -- maps each alias ("cat",
    # "owner", ...) to the list of (unqualified) column names selected for it, so `hydration.py`
    # knows how to split each flat result row back apart per-entity. `None` for everything else.
    labels_by_alias: dict[str, list[str]] | None = None
