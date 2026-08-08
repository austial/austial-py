"""``QueryBuilder`` fluent-chain behavior and its SQL-injection-safety guarantee -- values only
ever travel through bound params, never string-formatted into SQL text (see this package's
``driver/sqlalchemy_support.py`` module docstring for the mechanism).
"""

from __future__ import annotations

import pytest
from fixtures.data_source import sqlite_data_source
from fixtures.entities import Cat, Owner, Toy


@pytest.mark.asyncio
async def test_where_restarts_the_clause_and_and_where_appends():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    await manager.save(Cat(name="Tom", age=3))
    await manager.save(Cat(name="Jerry", age=1))

    qb = manager.create_query_builder(Cat, "cat")
    qb.where("cat.name = :name", {"name": "Tom"}).and_where("cat.age = :age", {"age": 3})
    assert [c.name for c in await qb.get_many()] == ["Tom"]

    # Calling .where() again discards the previous AND-chain entirely.
    qb.where("cat.name = :name", {"name": "Jerry"})
    assert [c.name for c in await qb.get_many()] == ["Jerry"]
    await ds.destroy()


@pytest.mark.asyncio
async def test_or_where_unions_conditions():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    await manager.save(Cat(name="Tom", age=3))
    await manager.save(Cat(name="Jerry", age=1))
    await manager.save(Cat(name="Spike", age=5))

    qb = manager.create_query_builder(Cat, "cat")
    qb.where("cat.age = :a", {"a": 3}).or_where("cat.age = :b", {"b": 5})
    assert {c.name for c in await qb.get_many()} == {"Tom", "Spike"}
    await ds.destroy()


@pytest.mark.asyncio
async def test_order_by_and_paging():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    await manager.save(Cat(name="Tom", age=3))
    await manager.save(Cat(name="Jerry", age=1))
    await manager.save(Cat(name="Spike", age=5))

    qb = manager.create_query_builder(Cat, "cat").order_by("cat.age", "ASC")
    assert [c.name for c in await qb.get_many()] == ["Jerry", "Tom", "Spike"]

    paged = manager.create_query_builder(Cat, "cat").order_by("cat.age", "ASC").skip(1).take(1)
    assert [c.name for c in await paged.get_many()] == ["Tom"]
    await ds.destroy()


@pytest.mark.asyncio
async def test_get_sql_never_inlines_bound_parameter_values():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager

    safe_sql = manager.create_query_builder(Cat, "cat").where("cat.name = :name", {"name": "Tom"}).get_sql()
    payload = "Tom'; DROP TABLE cat; --"
    payload_sql = manager.create_query_builder(Cat, "cat").where("cat.name = :name", {"name": payload}).get_sql()

    # The compiled SQL text is identical regardless of the bound value -- proof that the value
    # never gets formatted into the query string itself.
    assert safe_sql == payload_sql
    assert payload not in payload_sql
    assert ":name" in payload_sql or "?" in payload_sql
    await ds.destroy()


@pytest.mark.asyncio
async def test_where_with_injection_payload_value_does_not_execute_as_sql():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    await manager.save(Cat(name="Tom", age=3))

    payload = "Tom'; DROP TABLE cat; --"
    qb = manager.create_query_builder(Cat, "cat").where("cat.name = :name", {"name": payload})
    matched = await qb.get_many()

    assert matched == []
    # The `cat` table must still exist -- a real injection would have dropped it.
    assert len(await manager.find(Cat)) == 1
    await ds.destroy()
