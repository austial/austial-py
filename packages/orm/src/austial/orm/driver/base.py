"""``Driver`` -- the abstraction every concrete database backend implements.

Everything above this boundary (``QueryBuilder``, ``EntityManager``, ``Repository``,
``DataSource``) only ever talks to this ABC and the ``expression.py`` AST -- never to
``sqlalchemy`` directly. A future fully-custom driver (raw ``asyncpg``/``psycopg``/hand-rolled
MySQL protocol, no SQLAlchemy at all) is a drop-in: implement this ABC, translate the same
``SelectSpec``/``InsertSpec``/``UpdateSpec``/``DeleteSpec`` to that driver's native query
building, return :class:`~austial.orm.expression.DriverResult`. No other code needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import ClassVar

from austial.orm.expression import DeleteSpec, DriverResult, InsertSpec, SelectSpec, UpdateSpec


class Driver(ABC):
    dialect_name: ClassVar[str]

    @abstractmethod
    def __init__(self, url: str, **engine_kwargs: object) -> None:
        """Every concrete driver takes a connection ``url`` plus backend-specific engine
        kwargs -- declared here purely so callers that hold a ``type[Driver]`` (e.g.
        ``OrmModule``'s ``_DRIVER_BY_TYPE`` lookup) type-check when instantiating it
        generically; concrete drivers override this fully."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def execute_select(self, spec: SelectSpec) -> DriverResult: ...

    @abstractmethod
    async def execute_insert(self, spec: InsertSpec) -> DriverResult:
        """Returns a single-row :class:`DriverResult` carrying whatever the DB generated
        (e.g. an auto-increment primary key), keyed by column name."""

    @abstractmethod
    async def execute_update(self, spec: UpdateSpec) -> int:
        """Returns the number of rows affected."""

    @abstractmethod
    async def execute_delete(self, spec: DeleteSpec) -> int:
        """Returns the number of rows affected."""

    @abstractmethod
    async def execute_raw(self, sql: str, params: dict | None = None) -> DriverResult:
        """Escape hatch for callers that need raw SQL outside the entity-centric API (e.g.
        ``terminus``'s health-check ``SELECT 1``). Still goes through parameterized bind params,
        never string formatting."""

    @abstractmethod
    def transaction(self) -> AbstractAsyncContextManager[Driver]:
        """An async context manager yielding a ``Driver`` bound to one connection/transaction --
        every call made through that yielded driver participates in the same transaction, which
        commits on clean exit and rolls back on exception. Concrete drivers implement this with
        ``@contextlib.asynccontextmanager``."""

    @abstractmethod
    async def create_all_schemas(self, entities: Sequence[type]) -> None:
        """Dev/test convenience only (``DataSource(synchronize=True)``) -- issues ``CREATE TABLE``
        for every entity's mapped schema. Not the production path once migrations exist."""

    @abstractmethod
    def explain_select(self, spec: SelectSpec) -> str:
        """Compiles ``spec`` to SQL text *without* executing it -- purely for debugging/tests
        (``QueryBuilder.get_sql()``). Bind parameters stay as named placeholders (``:name``),
        never inlined as literal values, by construction."""
