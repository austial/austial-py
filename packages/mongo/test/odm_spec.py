from __future__ import annotations

from typing import Any

import pytest
from mongomock_motor import AsyncMongoMockClient
from pydantic import Field, ValidationError

from austial import AustialFactory, Injectable, Module
from austial.mongo import Document, Index, InjectModel, Model, MongoModule, Schema


@Schema(collection="cats", indexes=[Index("name", unique=True), Index(("age", -1))])
class Cat(Document):
    name: str = Field(min_length=1)
    age: int = 0


@Injectable()
class CatsService:
    def __init__(self, cats: Model[Cat] = InjectModel(Cat)):
        self.cats = cats


def make_app():
    client: Any = AsyncMongoMockClient()

    @Module(
        imports=[
            MongoModule.for_root(database="app", client_factory=lambda uri, **kw: client, connect_on_init=False),
            MongoModule.for_feature([Cat]),
        ],
        providers=[CatsService],
    )
    class Root:
        pass

    return AustialFactory.create(Root), client


async def test_crud_validation_ids_and_indexes() -> None:
    app, client = make_app()
    await app.init()
    cats = app.get(CatsService).cats

    tom = await cats.create({"name": "tom", "age": 3})
    assert isinstance(tom, Cat) and tom.id and tom.age == 3
    assert (await cats.find_by_id(tom.id)).name == "tom"  # str id -> ObjectId lookup
    assert (await cats.find_one({"id": tom.id})).id == tom.id

    await cats.create(Cat(name="kit", age=1))
    assert [c.name for c in await cats.find(sort=[("age", 1)])] == ["kit", "tom"]
    assert [c.name for c in await cats.find(sort=[("age", 1)], skip=1, limit=1)] == ["tom"]
    assert await cats.count({"age": {"$gt": 1}}) == 1 and await cats.exists({"name": "kit"})

    updated = await cats.update_by_id(tom.id, {"age": 4})
    assert updated.age == 4
    assert (await cats.update_one({"name": "tom"}, {"$inc": {"age": 1}})).age == 5
    assert (await cats.update_one({"name": "zed"}, {"age": 9}, upsert=True)).name == "zed"
    assert await cats.update_one({"name": "nobody"}, {"age": 1}) is None

    assert (await cats.aggregate([{"$group": {"_id": None, "total": {"$sum": "$age"}}}]))[0]["total"] == 15
    assert await cats.delete_by_id(tom.id) and not await cats.delete_by_id(tom.id)
    assert await cats.delete_many({"age": {"$lt": 100}}) == 2

    with pytest.raises(ValidationError):
        await cats.create({"name": ""})

    indexes = await client["app"]["cats"].index_information()
    assert any(info.get("unique") for info in indexes.values())  # the unique name index was created at init
    await app.close()


def test_schema_decorator_defaults_and_errors() -> None:
    @Schema()
    class Dog(Document):
        name: str

    from austial.mongo import schema_of

    assert schema_of(Dog).collection == "dogs"

    class Plain(Document):
        pass

    with pytest.raises(TypeError):
        schema_of(Plain)
