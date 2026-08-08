"""End-to-end DI wiring: ``OrmModule.for_root()``/``.for_feature()`` + ``@InjectRepository()``
resolve through ``austial-testing``'s ``Test.create_testing_module(...)``, the same way a real
app would wire a service to a repository -- proves the DI seam (``InjectRepository`` reusing
``InjectMarker`` directly, no container changes) actually works, not just that its pieces
type-check in isolation.

``entities=[Cat, Owner, Toy]`` must be passed together to ``OrmModule.for_root()`` even though
only ``Cat``'s repository is requested here: ``SchemaCatalog`` construction resolves every
declared relation's target entity eagerly, and ``Cat`` relates to both ``Owner`` and ``Toy``.
"""

from __future__ import annotations

import pytest
from fixtures.entities import Cat, Owner, Toy

from austial.common import Injectable
from austial.orm import DataSource, InjectRepository, OrmModule, Repository
from austial.testing import Test


@Injectable()
class CatsService:
    def __init__(self, cats: Repository[Cat] = InjectRepository(Cat)):
        self._cats = cats

    async def add(self, name: str) -> Cat:
        return await self._cats.save(Cat(name=name))

    async def all(self) -> list[Cat]:
        return await self._cats.find()


@pytest.mark.asyncio
async def test_inject_repository_resolves_end_to_end_through_di():
    orm_module = OrmModule.for_root(
        type_="sqlite", url="sqlite+aiosqlite:///:memory:", entities=[Owner, Cat, Toy], synchronize=True
    )
    feature_module = OrmModule.for_feature([Cat])

    testing_module = await Test.create_testing_module(
        imports=[orm_module, feature_module], providers=[CatsService]
    ).compile()

    data_source = testing_module.get(DataSource)
    await data_source.initialize()

    service = testing_module.get(CatsService)
    await service.add("Tom")

    cats = await service.all()
    assert [c.name for c in cats] == ["Tom"]
    await data_source.destroy()
