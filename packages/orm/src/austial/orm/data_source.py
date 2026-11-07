"""``DataSource`` -- mirrors TypeORM's ``DataSource`` (formerly ``Connection``): the single
object that owns one ``Driver`` and one entity ``SchemaCatalog``, and hands out
``EntityManager``/``Repository`` instances bound to them.

Constructing a ``DataSource`` is cheap and side-effect-free; the DB connection opens in ``initialize()``, which
``OrmModule``'s lifecycle hook calls when the application initialises (calling it yourself is harmless: it is
idempotent).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, TypeVar

import sqlalchemy as sa

from austial.orm.driver.base import Driver
from austial.orm.driver.sqlalchemy_support import SchemaCatalog
from austial.orm.entity_manager import EntityManager
from austial.orm.naming_strategy import DefaultNamingStrategy, NamingStrategy
from austial.orm.repository import Repository

R = TypeVar("R")
T = TypeVar("T")


class _LazyManager:
    """Forwards to ``data_source.manager`` at call time: a repository can exist before the connection does."""

    def __init__(self, data_source: DataSource):
        self._data_source = data_source

    def __getattr__(self, name: str) -> Any:
        return getattr(self._data_source.manager, name)


class DataSource:
    def __init__(
        self,
        driver: Driver,
        entities: Sequence[type],
        *,
        naming_strategy: NamingStrategy | None = None,
        synchronize: bool = False,
    ):
        self.driver = driver
        self._entities = list(entities)
        self._naming_strategy = naming_strategy or DefaultNamingStrategy()
        self._synchronize = synchronize
        self._catalog: SchemaCatalog | None = None
        self._manager: EntityManager | None = None

    @property
    def initialized(self) -> bool:
        return self._manager is not None

    async def initialize(self) -> DataSource:
        """Connects and builds the entity catalog. Idempotent: calling it again (a manual call plus ``OrmModule``'s own
        lifecycle hook, say) does nothing."""
        if self._manager is not None:
            return self
        await self.driver.connect()

        # Phase-1 pragmatic compromise (see `driver/base.py`'s module docstring): only the
        # SQLAlchemy-backed driver family (`PostgresDriver`/`SQLiteDriver`) exposes
        # `bind_schema()`/needs a `SchemaCatalog` at all -- a hand-rolled future driver with its
        # own schema representation simply wouldn't define it, so this call is best-effort rather
        # than part of the `Driver` ABC surface.
        bind_schema = getattr(self.driver, "bind_schema", None)
        if bind_schema is not None:
            bind_schema(self._entities, self._naming_strategy)

        self._catalog = SchemaCatalog(self._entities, self._naming_strategy)
        self._manager = EntityManager(self.driver, self._catalog)

        if self._synchronize:
            # Dev/test convenience only -- issues `CREATE TABLE` for every entity's mapped
            # schema. Not the production path once migrations exist (see plan's forward-compat
            # notes); production deployments should run migrations instead.
            await self.driver.create_all_schemas(self._entities)

        return self

    async def destroy(self) -> None:
        await self.driver.close()
        self._manager = None

    @property
    def manager(self) -> EntityManager:
        if self._manager is None:
            raise RuntimeError("DataSource.initialize() must be called before use.")
        return self._manager

    def get_repository(self, entity: type[T]) -> Repository[T]:
        # The repository may be built (injected) before initialize() runs, so it reaches the manager lazily.
        return Repository(entity, _LazyManager(self))  # type: ignore[arg-type]

    def get_metadata(self) -> sa.MetaData:
        """Returns the ``sqlalchemy.MetaData`` describing every entity this ``DataSource`` was
        constructed with -- what Alembic's ``env.py`` needs as ``target_metadata``::

            data_source = DataSource(driver, entities=[...])
            target_metadata = data_source.get_metadata()

        Building the entity ``SchemaCatalog`` only walks entity/relation metadata (no DB
        connection), so this is safe to call before ``initialize()`` too -- exactly what Alembic
        needs, since its process must not open the app's real connection pool just to import
        ``target_metadata`` at module load time.

        The one deliberate exception to this package's "nothing outside ``driver/`` imports
        ``sqlalchemy`` itself" rule (see ``driver/sqlalchemy_support.py``'s module docstring):
        Alembic's own API requires a real ``sqlalchemy.MetaData`` instance, so this method is the
        single documented seam where that type crosses the public API boundary.
        """
        if self._catalog is None:
            self._catalog = SchemaCatalog(self._entities, self._naming_strategy)
        return self._catalog.sqla_metadata

    async def transaction(self, callback: Callable[[EntityManager], Awaitable[R]]) -> R:
        """Opens one connection/transaction via ``Driver.transaction()``, binds a fresh
        ``EntityManager`` to it, and runs ``callback`` -- commits on clean return, rolls back on
        exception (both handled by the driver's transaction context manager)."""
        if self._catalog is None:
            raise RuntimeError("DataSource.initialize() must be called before use.")
        async with self.driver.transaction() as tx_driver:
            tx_manager = EntityManager(tx_driver, self._catalog)
            return await callback(tx_manager)
