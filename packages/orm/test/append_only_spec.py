"""Regression coverage for ``@Entity(append_only=True)`` -- framework-level enforcement of the
insert-only rule at the ``EntityManager`` choke point (see ``entity_manager.py``'s ``_save_one``/
``remove``/``update``/``delete``), rather than leaving it to app-layer service-code convention
("the service layer just doesn't call ``.update()``/``.delete()``").

``fixtures.entities.LedgerEntry`` is the dedicated append-only fixture; ``fixtures.entities.Order``
(a completely ordinary, non-append-only entity already used elsewhere in this suite) is reused
here to confirm the guard is opt-in and doesn't regress unrelated entities.
"""

from __future__ import annotations

import pytest
from fixtures.data_source import sqlite_data_source
from fixtures.entities import LedgerEntry, Order

from austial.orm import AppendOnlyViolationError, Column, Entity, PrimaryColumn
from austial.orm.metadata.column_types import String


@pytest.mark.asyncio
async def test_insert_succeeds_for_append_only_entity():
    ds = await sqlite_data_source([LedgerEntry])
    repo = ds.get_repository(LedgerEntry)

    saved = await repo.save(LedgerEntry(description="deposit", amount=100))

    assert saved.id is not None
    reloaded = await repo.find_one_by({"id": saved.id})
    assert reloaded is not None
    assert reloaded.description == "deposit"
    await ds.destroy()


@pytest.mark.asyncio
async def test_save_on_already_persisted_instance_raises():
    ds = await sqlite_data_source([LedgerEntry])
    repo = ds.get_repository(LedgerEntry)
    saved = await repo.save(LedgerEntry(description="deposit", amount=100))

    saved.amount = 200
    with pytest.raises(AppendOnlyViolationError) as exc_info:
        await repo.save(saved)

    assert "LedgerEntry" in str(exc_info.value)
    await ds.destroy()


@pytest.mark.asyncio
async def test_repository_update_raises():
    ds = await sqlite_data_source([LedgerEntry])
    repo = ds.get_repository(LedgerEntry)
    saved = await repo.save(LedgerEntry(description="deposit", amount=100))

    with pytest.raises(AppendOnlyViolationError):
        await repo.update(saved.id, {"amount": 200})
    await ds.destroy()


@pytest.mark.asyncio
async def test_repository_remove_raises():
    ds = await sqlite_data_source([LedgerEntry])
    repo = ds.get_repository(LedgerEntry)
    saved = await repo.save(LedgerEntry(description="deposit", amount=100))

    with pytest.raises(AppendOnlyViolationError):
        await repo.remove(saved)
    await ds.destroy()


@pytest.mark.asyncio
async def test_repository_delete_raises():
    ds = await sqlite_data_source([LedgerEntry])
    repo = ds.get_repository(LedgerEntry)
    saved = await repo.save(LedgerEntry(description="deposit", amount=100))

    with pytest.raises(AppendOnlyViolationError):
        await repo.delete(saved.id)
    await ds.destroy()


@pytest.mark.asyncio
async def test_non_append_only_entity_is_unaffected():
    ds = await sqlite_data_source([Order])
    repo = ds.get_repository(Order)
    saved = await repo.save(Order(group="alpha", total=3))

    saved.total = 42
    await repo.save(saved)
    result = await repo.update(saved.id, {"total": 99})
    assert result.affected == 1

    delete_result = await repo.delete(saved.id)
    assert delete_result.affected == 1
    await ds.destroy()


@Entity("keyed_audit", append_only=True)
class KeyedAudit:
    id: str = PrimaryColumn(type_=String(length=36))
    note: str = Column()


@pytest.mark.asyncio
async def test_insert_accepts_an_application_assigned_key_on_an_append_only_entity():
    ds = await sqlite_data_source([KeyedAudit])
    repo = ds.get_repository(KeyedAudit)

    inserted = await repo.insert(KeyedAudit(id="evt-1", note="hello"))

    assert inserted.id == "evt-1"
    reloaded = await repo.find_one_by({"id": "evt-1"})
    assert reloaded is not None and reloaded.note == "hello"
    # ``save()`` would treat the pre-set key as an UPDATE, which the append-only guard rejects.
    with pytest.raises(AppendOnlyViolationError):
        await repo.save(KeyedAudit(id="evt-2", note="x"))
    await ds.destroy()
