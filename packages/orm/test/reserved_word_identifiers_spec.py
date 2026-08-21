"""Regression coverage for identifiers that collide with a SQL reserved keyword.

``EntityManager`` uses an entity's table name as its query alias (see
``EntityManager._alias_for``) and splices ``f"{alias}.{column}"``-shaped text into the raw-SQL
``WhereFragment``/``OrderBySpec`` fragments it builds on the caller's behalf (from
``FindOptions.where``, bulk ``update()``/``delete()`` criteria, PK lookups, ``order_by`` tuples).
Left unquoted, a table or column named after a reserved keyword -- ``order``, ``group``, ``user``,
... -- produces a syntax error against any real SQL engine (reproduced here against SQLite, which
reserves ``ORDER`` the same way Postgres reserves both ``ORDER`` and ``USER``); see
``fixtures.entities.Order`` for the fixture entity (table ``order``, with a column also named
``group``) and ``austial.orm.identifier`` for the fix.
"""

from __future__ import annotations

import pytest
from fixtures.data_source import sqlite_data_source
from fixtures.entities import Order

from austial.orm import FindOptions


@pytest.mark.asyncio
async def test_find_by_and_find_one_by_against_reserved_word_table():
    ds = await sqlite_data_source([Order])
    repo = ds.get_repository(Order)
    await repo.save(Order(group="alpha", total=3))
    await repo.save(Order(group="beta", total=1))

    assert len(await repo.find_by({"group": "alpha"})) == 1
    found = await repo.find_one_by({"group": "beta"})
    assert found is not None
    assert found.group == "beta"
    assert await repo.find_one_by({"group": "nonexistent"}) is None
    await ds.destroy()


@pytest.mark.asyncio
async def test_where_or_group_against_reserved_word_table_and_column():
    ds = await sqlite_data_source([Order])
    repo = ds.get_repository(Order)
    await repo.save(Order(group="alpha", total=3))
    await repo.save(Order(group="beta", total=1))
    await repo.save(Order(group="gamma", total=5))

    result = await repo.find(FindOptions(where=[{"total": 3}, {"total": 5}]))
    assert {o.group for o in result} == {"alpha", "gamma"}
    await ds.destroy()


@pytest.mark.asyncio
async def test_order_by_reserved_word_column():
    ds = await sqlite_data_source([Order])
    repo = ds.get_repository(Order)
    await repo.save(Order(group="alpha", total=3))
    await repo.save(Order(group="beta", total=1))
    await repo.save(Order(group="gamma", total=5))

    result = await repo.find(FindOptions(order_by=[("group", "ASC")]))
    assert [o.group for o in result] == ["alpha", "beta", "gamma"]
    await ds.destroy()


@pytest.mark.asyncio
async def test_find_one_pk_lookup_against_reserved_word_table():
    ds = await sqlite_data_source([Order])
    repo = ds.get_repository(Order)
    saved = await repo.save(Order(group="alpha", total=3))

    reloaded = await repo.find_one_by({"id": saved.id})
    assert reloaded is not None
    assert reloaded.group == "alpha"
    await ds.destroy()


@pytest.mark.asyncio
async def test_save_updates_in_place_against_reserved_word_table():
    ds = await sqlite_data_source([Order])
    repo = ds.get_repository(Order)
    saved = await repo.save(Order(group="alpha", total=3))

    saved.total = 42
    await repo.save(saved)

    reloaded = await repo.find_one_by({"id": saved.id})
    assert reloaded is not None
    assert reloaded.total == 42
    assert len(await repo.find()) == 1  # an update, not a second insert
    await ds.destroy()


@pytest.mark.asyncio
async def test_bulk_update_by_pk_criteria_against_reserved_word_table():
    ds = await sqlite_data_source([Order])
    repo = ds.get_repository(Order)
    saved = await repo.save(Order(group="alpha", total=3))

    result = await repo.update(saved.id, {"total": 99})

    assert result.affected == 1
    reloaded = await repo.find_one_by({"id": saved.id})
    assert reloaded is not None
    assert reloaded.total == 99
    await ds.destroy()


@pytest.mark.asyncio
async def test_bulk_delete_by_pk_criteria_against_reserved_word_table():
    ds = await sqlite_data_source([Order])
    repo = ds.get_repository(Order)
    saved = await repo.save(Order(group="alpha", total=3))

    result = await repo.delete(saved.id)

    assert result.affected == 1
    assert await repo.find() == []
    await ds.destroy()


@pytest.mark.asyncio
async def test_remove_loaded_instance_against_reserved_word_table():
    ds = await sqlite_data_source([Order])
    repo = ds.get_repository(Order)
    saved = await repo.save(Order(group="alpha", total=3))

    await repo.remove(saved)

    assert await repo.find() == []
    await ds.destroy()
