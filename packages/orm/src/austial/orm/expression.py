"""SQL-free AST -- what :class:`~austial.orm.query_builder.QueryBuilder`/
:class:`~austial.orm.entity_manager.EntityManager` build up, and what a
:class:`~austial.orm.driver.base.Driver` compiles into real SQL.

Nothing in this module imports ``sqlalchemy``. This is the seam a future, fully-custom
(non-SQLAlchemy) driver would translate instead -- ``QueryBuilder``/``EntityManager``/
``Repository``/``DataSource`` never change regardless of what's on the other side of ``Driver``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

JoinType = Literal["INNER", "LEFT"]
OrderDirection = Literal["ASC", "DESC"]
Connector = Literal["AND", "OR"]


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
class SelectSpec:
    entity: type
    alias: str
    columns: list[str] | None = None  # None = all mapped columns
    wheres: list[WhereFragment] = field(default_factory=list)
    joins: list[JoinSpec] = field(default_factory=list)
    order_by: list[OrderBySpec] = field(default_factory=list)
    limit: int | None = None
    offset: int | None = None


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
