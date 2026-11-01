"""``Repository``/``EntityManager`` CRUD against an in-memory SQLite-backed ``DataSource`` --
insert-vs-update primary-key branching, bulk update/delete, and schema creation via
``synchronize=True``.
"""

from __future__ import annotations

import pytest
from fixtures.data_source import sqlite_data_source
from fixtures.entities import Cat, Owner, Toy

from austial.orm import FindOptions


@pytest.mark.asyncio
async def test_synchronize_creates_tables_for_every_entity():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    assert await ds.get_repository(Cat).find() == []
    assert await ds.get_repository(Owner).find() == []
    assert await ds.get_repository(Toy).find() == []
    await ds.destroy()


@pytest.mark.asyncio
async def test_save_inserts_when_primary_key_is_unset():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)

    saved = await repo.save(Cat(name="Tom", age=3))

    assert saved.id is not None
    assert saved.created_at is not None
    await ds.destroy()


@pytest.mark.asyncio
async def test_save_updates_in_place_when_primary_key_is_set():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)

    saved = await repo.save(Cat(name="Tom", age=3))
    saved.age = 4
    updated = await repo.save(saved)

    assert updated.id == saved.id
    reloaded = await repo.find_one_by({"id": saved.id})
    assert reloaded is not None
    assert reloaded.age == 4

    all_cats = await repo.find()
    assert len(all_cats) == 1  # an update, not a second insert
    await ds.destroy()


@pytest.mark.asyncio
async def test_save_accepts_a_sequence_and_returns_a_list():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)

    saved = await repo.save([Cat(name="Tom"), Cat(name="Jerry")])

    assert isinstance(saved, list)
    assert {c.name for c in saved} == {"Tom", "Jerry"}
    assert len(await repo.find()) == 2
    await ds.destroy()


@pytest.mark.asyncio
async def test_find_by_and_find_one_by():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)
    await repo.save(Cat(name="Tom", age=3))
    await repo.save(Cat(name="Jerry", age=1))

    assert len(await repo.find_by({"age": 3})) == 1
    found = await repo.find_one_by({"name": "Jerry"})
    assert found is not None
    assert found.name == "Jerry"
    assert await repo.find_one_by({"name": "Nonexistent"}) is None
    await ds.destroy()


@pytest.mark.asyncio
async def test_where_dict_is_and_and_list_of_dicts_is_or():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)
    await repo.save(Cat(name="Tom", age=3))
    await repo.save(Cat(name="Jerry", age=1))
    await repo.save(Cat(name="Spike", age=5))

    and_result = await repo.find(FindOptions(where={"name": "Tom", "age": 3}))
    assert [c.name for c in and_result] == ["Tom"]

    or_result = await repo.find(FindOptions(where=[{"age": 3}, {"age": 5}]))
    assert {c.name for c in or_result} == {"Tom", "Spike"}
    await ds.destroy()


@pytest.mark.asyncio
async def test_count_reflects_where_but_ignores_relations_and_paging():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)
    await repo.save(Cat(name="Tom"))
    await repo.save(Cat(name="Jerry"))

    assert await repo.count() == 2
    assert await repo.count(FindOptions(where={"name": "Tom"})) == 1
    await ds.destroy()


@pytest.mark.asyncio
async def test_bulk_update_by_criteria_does_not_load_rows_first():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)
    tom = await repo.save(Cat(name="Tom", age=3))

    result = await repo.update(tom.id, {"age": 10})

    assert result.affected == 1
    reloaded = await repo.find_one_by({"id": tom.id})
    assert reloaded is not None
    assert reloaded.age == 10
    await ds.destroy()


@pytest.mark.asyncio
async def test_bulk_delete_by_criteria():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)
    tom = await repo.save(Cat(name="Tom"))

    result = await repo.delete(tom.id)

    assert result.affected == 1
    assert await repo.find() == []
    await ds.destroy()


@pytest.mark.asyncio
async def test_remove_deletes_a_loaded_instance():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)
    tom = await repo.save(Cat(name="Tom"))

    await repo.remove(tom)

    assert await repo.find() == []
    await ds.destroy()
