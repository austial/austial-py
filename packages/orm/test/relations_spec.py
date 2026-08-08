"""Relation persistence and eager-loading -- ``ManyToOne``/``OneToMany`` (FK column, owned by the
``ManyToOne`` side) and ``ManyToMany`` (join table, owned by whichever side declares
``join_table``).

``test_saving_a_many_to_one_relation_persists_the_foreign_key`` is a regression test for a real
bug caught while building this suite: ``EntityManager._save_one()`` originally only wrote
``EntityMetadata.columns`` values, silently leaving FK columns (which live only in
``SchemaCatalog``, not ``EntityMetadata.columns``) NULL on every save.
"""

from __future__ import annotations

import pytest
from fixtures.data_source import sqlite_data_source
from fixtures.entities import Cat, Owner, Toy

from austial.orm import FindOptions, RelationNotFoundError


@pytest.mark.asyncio
async def test_saving_a_many_to_one_relation_persists_the_foreign_key():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    alice = await manager.save(Owner(name="Alice"))
    tom = await manager.save(Cat(name="Tom", owner=alice))

    raw = await ds.driver.execute_raw("SELECT owner_id FROM cat WHERE id = :id", {"id": tom.id})
    assert raw.rows[0]["owner_id"] == alice.id
    await ds.destroy()


@pytest.mark.asyncio
async def test_eager_loading_many_to_one_hydrates_the_related_instance():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    alice = await manager.save(Owner(name="Alice"))
    await manager.save(Cat(name="Tom", owner=alice))

    tom = await manager.find_one(Cat, FindOptions(where={"name": "Tom"}, relations=["owner"]))
    assert tom is not None
    assert tom.owner is not None
    assert tom.owner.name == "Alice"
    await ds.destroy()


@pytest.mark.asyncio
async def test_eager_loading_one_to_many_hydrates_the_related_list():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    alice = await manager.save(Owner(name="Alice"))
    await manager.save(Cat(name="Tom", owner=alice))
    await manager.save(Cat(name="Jerry", owner=alice))

    # `.find()`, not `.find_one()`/`.get_one()`: a to-many eager-loaded LEFT JOIN fans out one row
    # per child, and `get_one()`'s `LIMIT 1` would truncate that fan-out before hydration groups
    # it back into a list -- the same caveat real TypeORM documents for its own querybuilder.
    owners = await manager.find(Owner, FindOptions(where={"name": "Alice"}, relations=["cats"]))
    assert len(owners) == 1
    assert {c.name for c in owners[0].cats} == {"Tom", "Jerry"}
    await ds.destroy()


@pytest.mark.asyncio
async def test_eager_loading_many_to_many_hydrates_both_sides():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    tom = await manager.save(Cat(name="Tom"))
    mouse = await manager.save(Toy(name="Mouse"))
    ball = await manager.save(Toy(name="Ball"))

    # Phase 1 has no cascade/unit-of-work, so join-table rows are populated directly -- see
    # `EntityManager._owning_relation_values`'s docstring. Join table/columns are derived from
    # `DefaultNamingStrategy`: `cat_toy(cat_id, toy_id)` (owning side is `Cat.toys`).
    await ds.driver.execute_raw(
        "INSERT INTO cat_toy (cat_id, toy_id) VALUES (:cat_id, :toy_id)", {"cat_id": tom.id, "toy_id": mouse.id}
    )
    await ds.driver.execute_raw(
        "INSERT INTO cat_toy (cat_id, toy_id) VALUES (:cat_id, :toy_id)", {"cat_id": tom.id, "toy_id": ball.id}
    )

    cats = await manager.find(Cat, FindOptions(where={"name": "Tom"}, relations=["toys"]))
    assert len(cats) == 1
    assert {t.name for t in cats[0].toys} == {"Mouse", "Ball"}

    toys = await manager.find(Toy, FindOptions(where={"name": "Mouse"}, relations=["cats"]))
    assert len(toys) == 1
    assert {c.name for c in toys[0].cats} == {"Tom"}
    await ds.destroy()


@pytest.mark.asyncio
async def test_unknown_relation_name_raises():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    await manager.save(Cat(name="Tom"))

    with pytest.raises(RelationNotFoundError):
        await manager.find(Cat, FindOptions(relations=["nonexistent"]))
    await ds.destroy()
