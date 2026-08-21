"""``QueryBuilder`` -- the fluent chain API, mirrors TypeORM's ``createQueryBuilder()``.

Where-clauses are raw SQL fragments plus a *separate* bound-params dict (``.where("cat.name =
:name", {"name": name})``), exactly like real TypeORM's own querybuilder -- never a hand-rolled
expression parser. ``QueryBuilder`` never string-formats a value into SQL; it stores
:class:`~austial.orm.expression.WhereFragment` objects verbatim and the driver binds parameters
through the DBAPI, which is what actually makes this SQL-injection-safe.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import count
from typing import Any, Generic, Literal, Self, TypeVar

from austial.orm.driver.base import Driver
from austial.orm.driver.sqlalchemy_support import SchemaCatalog
from austial.orm.expression import (
    AggregateFn,
    AggregateSpec,
    Connector,
    JoinSpec,
    OrderBySpec,
    SelectSpec,
    WhereFragment,
)
from austial.orm.hydration import RowHydrator

T = TypeVar("T")


class QueryBuilder(Generic[T]):
    def __init__(self, entity: type[T], alias: str, driver: Driver, catalog: SchemaCatalog):
        self._driver = driver
        self._catalog = catalog
        self._spec = SelectSpec(entity=entity, alias=alias)
        self._param_seq = count()

    def select(self, *columns: str) -> Self:
        self._spec.columns = list(columns) or None
        return self

    def where(self, condition: str, params: dict[str, Any] | None = None) -> Self:
        """(Re)starts the WHERE clause -- any previously added conditions are discarded, matching
        TypeORM's ``.where()`` semantics (use ``.and_where()``/``.or_where()`` to add more)."""
        self._spec.wheres = [WhereFragment(condition, params or {}, "AND")]
        return self

    def and_where(self, condition: str, params: dict[str, Any] | None = None) -> Self:
        self._spec.wheres.append(WhereFragment(condition, params or {}, "AND"))
        return self

    def or_where(self, condition: str, params: dict[str, Any] | None = None) -> Self:
        self._spec.wheres.append(WhereFragment(condition, params or {}, "OR"))
        return self

    def _next_param_name(self) -> str:
        return f"v{next(self._param_seq)}"

    @staticmethod
    def _column_ref(column: str, cast_text: bool) -> str:
        return f"CAST({column} AS TEXT)" if cast_text else column

    def _eq_fragment(self, column: str, value: Any, cast_text: bool, connector: Connector) -> WhereFragment:
        name = self._next_param_name()
        return WhereFragment(f"{self._column_ref(column, cast_text)} = :{name}", {name: value}, connector)

    def _membership_fragment(
        self, column: str, values: Sequence[Any], cast_text: bool, negate: bool, connector: Connector
    ) -> WhereFragment:
        values = list(values)
        col_ref = self._column_ref(column, cast_text)
        if not values:
            # An empty IN() is invalid SQL; vacuous-truth semantics instead (NOT IN [] matches
            # everything, IN [] matches nothing) rather than raising.
            return WhereFragment("1 = 1" if negate else "1 = 0", {}, connector)
        names = [self._next_param_name() for _ in values]
        placeholders = ", ".join(f":{n}" for n in names)
        op = "NOT IN" if negate else "IN"
        return WhereFragment(f"{col_ref} {op} ({placeholders})", dict(zip(names, values, strict=True)), connector)

    def where_eq(self, column: str, value: Any, *, cast_text: bool = False) -> Self:
        """Single-value equality with a framework-generated bind param -- ``cast_text=True``
        wraps ``column`` in ``CAST(column AS TEXT)``, needed when comparing a native Postgres
        ``ENUM`` column against a plain string parameter (ANSI SQL, also works against SQLite)."""
        self._spec.wheres = [self._eq_fragment(column, value, cast_text, "AND")]
        return self

    def and_where_eq(self, column: str, value: Any, *, cast_text: bool = False) -> Self:
        self._spec.wheres.append(self._eq_fragment(column, value, cast_text, "AND"))
        return self

    def or_where_eq(self, column: str, value: Any, *, cast_text: bool = False) -> Self:
        self._spec.wheres.append(self._eq_fragment(column, value, cast_text, "OR"))
        return self

    def where_in(self, column: str, values: Sequence[Any], *, cast_text: bool = False) -> Self:
        """``column IN (...)`` with framework-generated bind params -- see ``.where_eq()`` for
        ``cast_text``."""
        self._spec.wheres = [self._membership_fragment(column, values, cast_text, False, "AND")]
        return self

    def and_where_in(self, column: str, values: Sequence[Any], *, cast_text: bool = False) -> Self:
        self._spec.wheres.append(self._membership_fragment(column, values, cast_text, False, "AND"))
        return self

    def or_where_in(self, column: str, values: Sequence[Any], *, cast_text: bool = False) -> Self:
        self._spec.wheres.append(self._membership_fragment(column, values, cast_text, False, "OR"))
        return self

    def where_not_in(self, column: str, values: Sequence[Any], *, cast_text: bool = False) -> Self:
        """``column NOT IN (...)`` with framework-generated bind params -- see ``.where_eq()`` for
        ``cast_text``."""
        self._spec.wheres = [self._membership_fragment(column, values, cast_text, True, "AND")]
        return self

    def and_where_not_in(self, column: str, values: Sequence[Any], *, cast_text: bool = False) -> Self:
        self._spec.wheres.append(self._membership_fragment(column, values, cast_text, True, "AND"))
        return self

    def or_where_not_in(self, column: str, values: Sequence[Any], *, cast_text: bool = False) -> Self:
        self._spec.wheres.append(self._membership_fragment(column, values, cast_text, True, "OR"))
        return self

    def left_join_and_select(self, relation: str, alias: str) -> Self:
        self._spec.joins.append(JoinSpec(relation, alias, "LEFT", select=True))
        return self

    def inner_join_and_select(self, relation: str, alias: str) -> Self:
        self._spec.joins.append(JoinSpec(relation, alias, "INNER", select=True))
        return self

    def inner_join(self, relation: str, alias: str) -> Self:
        self._spec.joins.append(JoinSpec(relation, alias, "INNER", select=False))
        return self

    def order_by(self, column: str, direction: Literal["ASC", "DESC"] = "ASC") -> Self:
        self._spec.order_by = [OrderBySpec(column, direction)]
        return self

    def add_order_by(self, column: str, direction: Literal["ASC", "DESC"] = "ASC") -> Self:
        self._spec.order_by.append(OrderBySpec(column, direction))
        return self

    def limit(self, n: int) -> Self:
        self._spec.limit = n
        return self

    def offset(self, n: int) -> Self:
        self._spec.offset = n
        return self

    def take(self, n: int) -> Self:
        return self.limit(n)

    def skip(self, n: int) -> Self:
        return self.offset(n)

    def group_by(self, *columns: str) -> Self:
        """(Re)starts the GROUP BY clause -- physical column names on the root entity, no
        dotted/joined paths (Phase-1 scope, matches ``EntityManager.count()``). Pair with
        ``.get_aggregate_raw()`` for grouped aggregates (e.g. AUM broken down by currency)."""
        self._spec.group_by = list(columns)
        return self

    async def get_many(self) -> list[T]:
        result = await self._driver.execute_select(self._spec)
        return RowHydrator(self._catalog).hydrate(self._spec, result)

    async def get_one(self) -> T | None:
        original_limit = self._spec.limit
        self._spec.limit = 1
        try:
            rows = await self.get_many()
        finally:
            self._spec.limit = original_limit
        return rows[0] if rows else None

    async def get_many_and_count(self) -> tuple[list[T], int]:
        entities = await self.get_many()
        count_spec = SelectSpec(
            entity=self._spec.entity, alias=self._spec.alias, wheres=self._spec.wheres, joins=self._spec.joins
        )
        result = await self._driver.execute_select(count_spec)
        return entities, len(result.rows)

    async def get_raw_many(self) -> list[dict[str, Any]]:
        result = await self._driver.execute_select(self._spec)
        return result.rows

    async def get_raw_one(self) -> dict[str, Any] | None:
        rows = await self.get_raw_many()
        return rows[0] if rows else None

    async def get_aggregate_raw(self, fn: AggregateFn, column: str) -> list[dict[str, Any]]:
        """Compiles a ``SUM``/``AVG``/``MIN``/``MAX`` over ``column`` (a physical column name --
        no entity-metadata translation, unlike ``Repository.sum()``/``EntityManager.aggregate()``,
        which build on this) against the current WHERE/``.group_by()`` clauses, and executes it.
        Returns raw rows: one ``{"value": ...}`` dict without ``.group_by()``, or one dict per
        group (its columns' names + ``"value"``) with it."""
        self._spec.aggregate = AggregateSpec(fn, column)
        result = await self._driver.execute_select(self._spec)
        return result.rows

    def get_sql(self) -> str:
        """Compiles without executing -- a debug helper, also used in tests to assert
        parameterization never inlines user-supplied values into the SQL text."""
        return self._driver.explain_select(self._spec)
