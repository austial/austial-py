"""``DataSource.transaction()`` -- commit-on-clean-return, rollback-on-exception, and visibility
of a transaction's own writes to itself before it commits.
"""

from __future__ import annotations

import pytest
from fixtures.data_source import sqlite_data_source
from fixtures.entities import Cat, Owner, Toy


class _Boom(Exception):
    pass


@pytest.mark.asyncio
async def test_transaction_commits_on_clean_return():
    ds = await sqlite_data_source([Owner, Cat, Toy])

    async def _work(manager):
        await manager.save(Cat(name="Tom"))

    await ds.transaction(_work)

    assert len(await ds.manager.find(Cat)) == 1
    await ds.destroy()


@pytest.mark.asyncio
async def test_transaction_rolls_back_on_exception():
    ds = await sqlite_data_source([Owner, Cat, Toy])

    async def _work(manager):
        await manager.save(Cat(name="Tom"))
        raise _Boom("simulated failure")

    with pytest.raises(_Boom):
        await ds.transaction(_work)

    assert await ds.manager.find(Cat) == []
    await ds.destroy()


@pytest.mark.asyncio
async def test_transaction_manager_sees_its_own_writes_before_commit():
    ds = await sqlite_data_source([Owner, Cat, Toy])

    async def _work(manager):
        await manager.save(Owner(name="Alice"))
        found = await manager.find_one_by(Owner, {"name": "Alice"})
        assert found is not None
        assert found.name == "Alice"

    await ds.transaction(_work)
    await ds.destroy()
