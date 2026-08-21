"""``QueryBuilder``'s ``.where_in()``/``.where_not_in()``/``.where_eq()`` family (framework-
generated bind params, optional ``cast_text``) and ``FindOptions.where``'s ``In``/``NotIn``
markers -- closes the raw-SQL-``CAST`` workaround gap for comparing native-``ENUM`` columns.
"""

from __future__ import annotations

import pytest
from fixtures.data_source import sqlite_data_source
from fixtures.entities import Cat, Owner, Subscriber, Toy

from austial.orm import FindOptions, In, NotIn


@pytest.mark.asyncio
async def test_and_where_in_and_not_in_produce_parameterized_sql_and_correct_results():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    await manager.save(Cat(name="Tom", age=3))
    await manager.save(Cat(name="Jerry", age=1))
    await manager.save(Cat(name="Spike", age=5))

    in_sql = manager.create_query_builder(Cat, "cat").and_where_in("cat.age", [3, 5]).get_sql()
    assert "IN" in in_sql
    assert "3" not in in_sql and "5" not in in_sql  # values never inlined, only bind placeholders

    in_result = await manager.create_query_builder(Cat, "cat").where_in("cat.age", [3, 5]).get_many()
    assert {c.name for c in in_result} == {"Tom", "Spike"}

    not_in_result = await manager.create_query_builder(Cat, "cat").where_not_in("cat.age", [3, 5]).get_many()
    assert [c.name for c in not_in_result] == ["Jerry"]
    await ds.destroy()


@pytest.mark.asyncio
async def test_where_in_with_empty_values_is_vacuously_false_and_not_in_vacuously_true():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    await manager.save(Cat(name="Tom", age=3))

    assert await manager.create_query_builder(Cat, "cat").where_in("cat.age", []).get_many() == []
    all_cats = await manager.create_query_builder(Cat, "cat").where_not_in("cat.age", []).get_many()
    assert [c.name for c in all_cats] == ["Tom"]
    await ds.destroy()


@pytest.mark.asyncio
async def test_where_eq_and_and_where_eq_chain_without_param_name_collisions():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    await manager.save(Cat(name="Tom", age=3))
    await manager.save(Cat(name="Tom", age=4))

    qb = manager.create_query_builder(Cat, "cat").where_eq("cat.name", "Tom").and_where_eq("cat.age", 4)
    assert [c.age for c in await qb.get_many()] == [4]
    await ds.destroy()


@pytest.mark.asyncio
async def test_cast_text_round_trips_against_an_enum_typed_column():
    ds = await sqlite_data_source([Subscriber])
    manager = ds.manager
    await manager.save(Subscriber(status="MANUAL_REVIEW"))
    await manager.save(Subscriber(status="VERIFIED"))

    qb = manager.create_query_builder(Subscriber, "s").where_eq("s.status", "MANUAL_REVIEW", cast_text=True)
    assert "CAST(s.status AS TEXT)" in qb.get_sql()

    review = await qb.get_many()
    assert [r.status for r in review] == ["MANUAL_REVIEW"]

    not_verified = await (
        manager.create_query_builder(Subscriber, "s").where_not_in("s.status", ["VERIFIED"], cast_text=True).get_many()
    )
    assert [r.status for r in not_verified] == ["MANUAL_REVIEW"]
    await ds.destroy()


@pytest.mark.asyncio
async def test_find_options_where_in_and_not_in():
    ds = await sqlite_data_source([Subscriber])
    repo = ds.get_repository(Subscriber)
    await repo.save(Subscriber(status="PENDING"))
    await repo.save(Subscriber(status="MANUAL_REVIEW"))
    await repo.save(Subscriber(status="VERIFIED"))

    in_result = await repo.find(FindOptions(where={"status": In(["PENDING", "MANUAL_REVIEW"])}))
    assert {r.status for r in in_result} == {"PENDING", "MANUAL_REVIEW"}

    not_in_result = await repo.find(FindOptions(where={"status": NotIn(["VERIFIED", "REJECTED"])}))
    assert {r.status for r in not_in_result} == {"PENDING", "MANUAL_REVIEW"}
    await ds.destroy()


@pytest.mark.asyncio
async def test_find_options_where_in_with_empty_values_matches_nothing():
    ds = await sqlite_data_source([Subscriber])
    repo = ds.get_repository(Subscriber)
    await repo.save(Subscriber(status="PENDING"))

    assert await repo.find(FindOptions(where={"status": In([])})) == []
    all_rows = await repo.find(FindOptions(where={"status": NotIn([])}))
    assert [r.status for r in all_rows] == ["PENDING"]
    await ds.destroy()
