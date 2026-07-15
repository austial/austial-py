"""``DatabaseModule`` -- mirrors ``@nestjs/typeorm``'s ``TypeOrmModule.forRoot[Async]()``.

Backed by SQLAlchemy's async engine; defaults to a local sqlite file so a
freshly generated project works with zero external services.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule

DATABASE_ENGINE = "DATABASE_ENGINE"
DATABASE_SESSION_FACTORY = "DATABASE_SESSION_FACTORY"


@Module()
class DatabaseModule:
    """Import via ``DatabaseModule.for_root(url=...)`` or
    ``DatabaseModule.for_root_async(use_factory=..., inject=[ConfigService])``,
    mirroring Nest's TypeORM dynamic-module conventions. Exposes two tokens
    other providers can ``Inject(...)``: ``DATABASE_ENGINE`` and
    ``DATABASE_SESSION_FACTORY``."""

    @staticmethod
    def for_root(url: str = "sqlite+aiosqlite:///./austial.db", **engine_kwargs: Any) -> DynamicModule:
        engine = create_async_engine(url, **engine_kwargs)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return DynamicModule(
            module=DatabaseModule,
            providers=[
                {"provide": DATABASE_ENGINE, "useValue": engine},
                {"provide": DATABASE_SESSION_FACTORY, "useValue": session_factory},
            ],
            exports=[DATABASE_ENGINE, DATABASE_SESSION_FACTORY],
        )

    @staticmethod
    def for_root_async(*, use_factory: Callable[..., str], inject: Sequence[Any] = ()) -> DynamicModule:
        def _build_engine(*deps: Any):
            return create_async_engine(use_factory(*deps))

        def _build_session_factory(engine: Any):
            return async_sessionmaker(engine, expire_on_commit=False)

        return DynamicModule(
            module=DatabaseModule,
            providers=[
                {"provide": DATABASE_ENGINE, "useFactory": _build_engine, "inject": list(inject)},
                {
                    "provide": DATABASE_SESSION_FACTORY,
                    "useFactory": _build_session_factory,
                    "inject": [DATABASE_ENGINE],
                },
            ],
            exports=[DATABASE_ENGINE, DATABASE_SESSION_FACTORY],
        )
