"""``OrmModule`` -- mirrors ``@nestjs/typeorm``'s ``TypeOrmModule.forRoot()``/``forFeature()``.

Import ``OrmModule.for_root(...)`` in ``AppModule``'s ``imports=[...]`` once, to register a
single app-wide ``DataSource``; import ``OrmModule.for_feature([Cat, Owner])`` in whichever
feature module needs ``@InjectRepository(Cat)``/``@InjectRepository(Owner)``.

Lifecycle gap (see ``data_source.py``'s docstring for the full explanation): ``austial-core``'s
``module_scanner`` is synchronous and has no async module-init hook, so ``for_root()``/
``for_root_async()`` only *construct* the ``Driver``+``DataSource`` at module-scan time (cheap --
``create_async_engine()`` itself is lazy, no connection opens yet). The app entrypoint must still
call ``await app.get(DataSource).initialize()`` itself before serving requests -- exactly the
pattern vanilla (non-Nest) TypeORM uses, and the first thing to simplify once ``austial-core``
grows real lifecycle hooks.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal

from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule
from austial.orm.data_source import DataSource
from austial.orm.decorators.inject_repository import repository_token
from austial.orm.driver.base import Driver
from austial.orm.driver.postgres import PostgresDriver
from austial.orm.driver.sqlite import SQLiteDriver
from austial.orm.naming_strategy import NamingStrategy

DriverType = Literal["postgres", "sqlite"]

_DRIVER_BY_TYPE: dict[str, type[Driver]] = {"postgres": PostgresDriver, "sqlite": SQLiteDriver}


def _make_repository_factory(entity: type) -> Callable[[DataSource], Any]:
    # A plain closure over `ds` would close over the *last* `entity` in the loop below for every
    # provider -- the `entity=entity` default binds it per-iteration instead.
    def factory(data_source: DataSource, entity: type = entity) -> Any:
        return data_source.get_repository(entity)

    return factory


@Module()
class OrmModule:
    @staticmethod
    def for_root(
        *,
        type_: DriverType,
        url: str,
        entities: Sequence[type],
        synchronize: bool = False,
        naming_strategy: NamingStrategy | None = None,
        **driver_kwargs: Any,
    ) -> DynamicModule:
        driver_cls = _DRIVER_BY_TYPE[type_]
        driver = driver_cls(url, **driver_kwargs)
        data_source = DataSource(driver, entities, naming_strategy=naming_strategy, synchronize=synchronize)
        return DynamicModule(
            module=OrmModule,
            providers=[{"provide": DataSource, "useValue": data_source}],
            exports=[DataSource],
        )

    @staticmethod
    def for_root_async(
        *,
        use_factory: Callable[..., dict[str, Any]],
        inject: Sequence[Any] = (),
        entities: Sequence[type],
        synchronize: bool = False,
        naming_strategy: NamingStrategy | None = None,
    ) -> DynamicModule:
        """``use_factory(*deps)`` must return a dict shaped like ``for_root()``'s
        ``type_``/``url``/driver-kwargs (``entities``/``synchronize`` stay static, passed here
        directly -- they describe the app's schema, not runtime config)."""

        def _build_data_source(*deps: Any) -> DataSource:
            options = dict(use_factory(*deps))
            driver_cls = _DRIVER_BY_TYPE[options.pop("type_")]
            url = options.pop("url")
            driver = driver_cls(url, **options)
            return DataSource(driver, entities, naming_strategy=naming_strategy, synchronize=synchronize)

        return DynamicModule(
            module=OrmModule,
            providers=[{"provide": DataSource, "useFactory": _build_data_source, "inject": list(inject)}],
            exports=[DataSource],
        )

    @staticmethod
    def for_feature(entities: Sequence[type]) -> DynamicModule:
        providers = [
            {
                "provide": repository_token(entity),
                "useFactory": _make_repository_factory(entity),
                "inject": [DataSource],
            }
            for entity in entities
        ]
        return DynamicModule(
            module=OrmModule,
            providers=providers,
            exports=[p["provide"] for p in providers],
        )
