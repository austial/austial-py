"""``Repository``/``EntityManager``/``QueryBuilder`` aggregate support (``SUM``/``AVG``/``MIN``/
``MAX``, optionally ``GROUP BY``) -- closes the gap ``count()`` deliberately doesn't cover (see
``entity_manager.py``'s ``aggregate()`` docstring). Same WHERE-only (no joins/paging) scope as
``count()``, plus optional single-level ``GROUP BY`` on the root entity's own columns.
"""

from __future__ import annotations

import pytest
from fixtures.data_source import sqlite_data_source
from fixtures.entities import Cat, Owner, Toy

from austial.orm.exceptions import OrmError


@pytest.mark.asyncio
async def test_sum_totals_a_numeric_column_across_matching_rows():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)
    await repo.save(Cat(name="Tom", age=3))
    await repo.save(Cat(name="Jerry", age=1))
    await repo.save(Cat(name="Spike", age=5))

    assert await repo.sum("age") == 9.0
    await ds.destroy()


@pytest.mark.asyncio
async def test_sum_respects_criteria_the_same_way_count_does():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)
    await repo.save(Cat(name="Tom", age=3))
    await repo.save(Cat(name="Tom", age=4))
    await repo.save(Cat(name="Jerry", age=1))

    assert await repo.sum("age", criteria={"name": "Tom"}) == 7.0
    await ds.destroy()


@pytest.mark.asyncio
async def test_sum_of_zero_matching_rows_normalizes_null_to_zero():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)
    await repo.save(Cat(name="Tom", age=3))

    assert await repo.sum("age", criteria={"name": "Nonexistent"}) == 0.0
    await ds.destroy()


@pytest.mark.asyncio
async def test_sum_with_group_by_returns_one_row_per_group():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)
    await repo.save(Cat(name="Tom", age=3))
    await repo.save(Cat(name="Tom", age=4))
    await repo.save(Cat(name="Jerry", age=1))

    rows = await repo.sum("age", group_by=["name"])

    assert {(r["name"], r["value"]) for r in rows} == {("Tom", 7.0), ("Jerry", 1.0)}
    await ds.destroy()


@pytest.mark.asyncio
async def test_group_by_omits_groups_with_no_matching_rows():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)
    await repo.save(Cat(name="Tom", age=3))

    rows = await repo.sum("age", criteria={"name": "Nonexistent"}, group_by=["name"])

    assert rows == []
    await ds.destroy()


@pytest.mark.asyncio
async def test_aggregate_supports_avg_min_max():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)
    await repo.save(Cat(name="Tom", age=3))
    await repo.save(Cat(name="Jerry", age=1))
    await repo.save(Cat(name="Spike", age=5))

    assert await repo.aggregate("AVG", "age") == 3.0
    assert await repo.aggregate("MIN", "age") == 1.0
    assert await repo.aggregate("MAX", "age") == 5.0
    await ds.destroy()


@pytest.mark.asyncio
async def test_aggregate_raises_for_unknown_column():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)

    with pytest.raises(OrmError):
        await repo.sum("not_a_real_column")
    await ds.destroy()


@pytest.mark.asyncio
async def test_aggregate_raises_for_unknown_group_by_column():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    repo = ds.get_repository(Cat)

    with pytest.raises(OrmError):
        await repo.sum("age", group_by=["not_a_real_column"])
    await ds.destroy()


@pytest.mark.asyncio
async def test_query_builder_get_aggregate_raw_is_the_lower_level_seam():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    await manager.save(Cat(name="Tom", age=3))
    await manager.save(Cat(name="Jerry", age=1))

    qb = manager.create_query_builder(Cat, "cat").where("cat.age > :min_age", {"min_age": 0})
    rows = await qb.get_aggregate_raw("SUM", "age")

    assert rows == [{"value": 4}]
    await ds.destroy()


@pytest.mark.asyncio
async def test_query_builder_group_by_restarts_the_clause():
    ds = await sqlite_data_source([Owner, Cat, Toy])
    manager = ds.manager
    await manager.save(Cat(name="Tom", age=3))
    await manager.save(Cat(name="Tom", age=4))

    qb = manager.create_query_builder(Cat, "cat").group_by("name").group_by("age")
    # Calling .group_by() again discards the previous grouping entirely -- grouping by `age`
    # alone means every row here forms its own group.
    rows = await qb.get_aggregate_raw("SUM", "age")

    assert {r["age"] for r in rows} == {3, 4}
    await ds.destroy()
