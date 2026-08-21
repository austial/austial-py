"""``Repository`` -- mirrors TypeORM's ``Repository<Entity>``: a thin, single-entity-bound
facade over :class:`~austial.orm.entity_manager.EntityManager`. This is what
``OrmModule.for_feature([...])``/``@InjectRepository(Entity)`` hand out via DI -- consumers never
construct one directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar, overload

from austial.orm.entity_manager import DeleteResult, EntityManager, FindOptions, UpdateResult
from austial.orm.expression import AggregateFn
from austial.orm.query_builder import QueryBuilder

T = TypeVar("T")

Criteria = dict[str, Any] | int | str


class Repository(Generic[T]):
    def __init__(self, entity: type[T], manager: EntityManager):
        self.entity = entity
        self.manager = manager

    def create_query_builder(self, alias: str) -> QueryBuilder[T]:
        return self.manager.create_query_builder(self.entity, alias)

    async def find(self, options: FindOptions | None = None) -> list[T]:
        return await self.manager.find(self.entity, options)

    async def find_one(self, options: FindOptions) -> T | None:
        return await self.manager.find_one(self.entity, options)

    async def find_by(self, criteria: dict[str, Any]) -> list[T]:
        return await self.manager.find_by(self.entity, criteria)

    async def find_one_by(self, criteria: dict[str, Any]) -> T | None:
        return await self.manager.find_one_by(self.entity, criteria)

    async def count(self, options: FindOptions | None = None) -> int:
        return await self.manager.count(self.entity, options)

    @overload
    async def aggregate(
        self, fn: AggregateFn, column: str, criteria: dict[str, Any] | None = None, group_by: None = None
    ) -> float: ...

    @overload
    async def aggregate(
        self, fn: AggregateFn, column: str, criteria: dict[str, Any] | None = None, *, group_by: Sequence[str]
    ) -> list[dict[str, Any]]: ...

    async def aggregate(
        self,
        fn: AggregateFn,
        column: str,
        criteria: dict[str, Any] | None = None,
        group_by: Sequence[str] | None = None,
    ) -> float | list[dict[str, Any]]:
        return await self.manager.aggregate(self.entity, fn, column, criteria=criteria, group_by=group_by)

    @overload
    async def sum(self, column: str, criteria: dict[str, Any] | None = None, group_by: None = None) -> float: ...

    @overload
    async def sum(
        self, column: str, criteria: dict[str, Any] | None = None, *, group_by: Sequence[str]
    ) -> list[dict[str, Any]]: ...

    async def sum(
        self, column: str, criteria: dict[str, Any] | None = None, group_by: Sequence[str] | None = None
    ) -> float | list[dict[str, Any]]:
        return await self.manager.sum(self.entity, column, criteria=criteria, group_by=group_by)

    async def save(self, entity_instance: T | Sequence[T]) -> T | list[T]:
        return await self.manager.save(entity_instance)

    async def remove(self, entity_instance: T | Sequence[T]) -> None:
        await self.manager.remove(entity_instance)

    async def update(self, criteria: Criteria, partial: dict[str, Any]) -> UpdateResult:
        return await self.manager.update(self.entity, criteria, partial)

    async def delete(self, criteria: Criteria) -> DeleteResult:
        return await self.manager.delete(self.entity, criteria)
