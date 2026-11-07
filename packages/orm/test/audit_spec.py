"""``austial.audit`` unit tests.

Covers the load-bearing behaviours a compliance auditor would test in
review:

- ``AuditLogService.record`` + ``query`` round-trip through the
  in-memory store.
- ``query`` honours ``actor``, ``action``, ``since``/``until`` filters and
  ``limit``.
- ``AuditedInterceptor`` records ``outcome="success"`` on the happy path.
- ``AuditedInterceptor`` records ``outcome="failure"`` and re-raises when
  the handler throws.
- ``resource_id_from="path:id"`` and ``result.id`` resolution.
- Retention eviction removes stale records but preserves ones under a
  legal hold.
- ``OrmAuditStore.record`` saves an ``AuditLogEntry`` via a mock
  repository; the append-only ORM entity is verified separately.
- Attempting to update an ``AuditLogEntry`` via a real ORM raises
  ``AppendOnlyViolationError`` -- proved end-to-end by wiring a real
  ``EntityManager`` against a mock driver.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from austial.audit import (
    AuditConfig,
    Audited,
    AuditedInterceptor,
    AuditEvent,
    AuditLogEntry,
    AuditLogService,
    InMemoryAuditStore,
    OrmAuditStore,
    get_audit_spec,
)
from austial.common import ExecutionContext
from austial.common.interceptors.base import CallHandler
from austial.orm.exceptions import AppendOnlyViolationError


class _FakeCtx(ExecutionContext):
    def __init__(self, request, controller_class, handler):
        self._req, self._cls, self._h = request, controller_class, handler

    def get_request(self):
        return self._req

    def get_class(self):
        return self._cls

    def get_handler(self):
        return self._h


def _request(*, principal=None, tenant=None, path_params=None, request_id=None):
    state = SimpleNamespace()
    if principal is not None:
        state.user = principal
    if tenant is not None:
        state.tenant = tenant
    if request_id is not None:
        state.request_id = request_id
    return SimpleNamespace(state=state, path_params=path_params or {})


def _service() -> tuple[AuditLogService, InMemoryAuditStore]:
    store = InMemoryAuditStore()
    return AuditLogService(store, AuditConfig()), store


# ---------------------------------------------------------------------------
# AuditLogService round-trip + filters


@pytest.mark.asyncio
async def test_record_and_query_round_trip():
    svc, _ = _service()
    ev = AuditEvent(action="funds.create", resource_type="Fund", actor="user-1", resource_id="F1")
    await svc.record(ev)

    result = await svc.query()
    assert len(result) == 1
    assert result[0].id == ev.id
    assert result[0].action == "funds.create"


@pytest.mark.asyncio
async def test_query_filters_by_actor_and_action():
    svc, _ = _service()
    await svc.record(AuditEvent(action="funds.create", resource_type="Fund", actor="alice"))
    await svc.record(AuditEvent(action="funds.delete", resource_type="Fund", actor="alice"))
    await svc.record(AuditEvent(action="funds.create", resource_type="Fund", actor="bob"))

    by_alice = await svc.query(actor="alice")
    assert {e.action for e in by_alice} == {"funds.create", "funds.delete"}

    creates = await svc.query(action="funds.create")
    assert {e.actor for e in creates} == {"alice", "bob"}

    # ``subject`` is an alias for ``actor``
    subject_alias = await svc.query(subject="bob")
    assert len(subject_alias) == 1 and subject_alias[0].actor == "bob"


@pytest.mark.asyncio
async def test_query_filters_by_tenant_id():
    """A tenant's own compliance officer must only ever see their own tenant's events; a
    platform-operator role queries a specific tenant explicitly. Without this filter, ``query()``
    returns every tenant's events mixed together -- a cross-tenant audit-log leak."""
    svc, _ = _service()
    await svc.record(AuditEvent(action="kyc.decide", resource_type="KycCase", tenant_id="tenant-a"))
    await svc.record(AuditEvent(action="kyc.decide", resource_type="KycCase", tenant_id="tenant-b"))

    only_a = await svc.query(tenant_id="tenant-a")
    assert {e.tenant_id for e in only_a} == {"tenant-a"}


@pytest.mark.asyncio
async def test_orm_store_query_filters_by_tenant_id():
    from austial.orm import DataSource, SQLiteDriver

    data_source = await DataSource(
        SQLiteDriver("sqlite+aiosqlite:///:memory:"), [AuditLogEntry], synchronize=True
    ).initialize()
    try:
        store = OrmAuditStore(data_source.get_repository(AuditLogEntry))
        await store.record(AuditEvent(action="a", resource_type="R", tenant_id="tenant-a"))
        await store.record(AuditEvent(action="a", resource_type="R", tenant_id="tenant-b"))

        only_a = await store.query(tenant_id="tenant-a")
        assert {e.tenant_id for e in only_a} == {"tenant-a"}
    finally:
        await data_source.destroy()


@pytest.mark.asyncio
async def test_query_filters_by_date_and_limit():
    svc, _ = _service()
    now = datetime.now(UTC)
    old = AuditEvent(action="a", resource_type="R", actor="u")
    # older event: rebuild the frozen dataclass with a back-dated timestamp
    from dataclasses import replace

    old = replace(old, timestamp=now - timedelta(days=10))
    recent = AuditEvent(action="a", resource_type="R", actor="u")
    await svc.record(old)
    await svc.record(recent)

    since = now - timedelta(days=1)
    recent_only = await svc.query(since=since)
    assert len(recent_only) == 1

    all_capped = await svc.query(limit=1)
    assert len(all_capped) == 1


# ---------------------------------------------------------------------------
# AuditedInterceptor: success/failure paths


@pytest.mark.asyncio
async def test_interceptor_records_success_and_passes_result_through():
    svc, store = _service()
    interceptor = AuditedInterceptor(svc)

    @Audited("funds.create", resource_type="Fund", resource_id_from="result.id")
    async def handler():
        return {"id": "F42", "name": "Alpha"}

    req = _request(
        principal=SimpleNamespace(subject="user-7", claims={}),
        tenant=SimpleNamespace(tenant_id="acme"),
        request_id="req-abc",
    )
    ctx = _FakeCtx(req, object, handler)

    async def next_call():
        return await handler()

    result = await interceptor.intercept(ctx, CallHandler(next_call))
    assert result == {"id": "F42", "name": "Alpha"}

    events = await svc.query()
    assert len(events) == 1
    ev = events[0]
    assert ev.outcome == "success"
    assert ev.actor == "user-7"
    assert ev.tenant_id == "acme"
    assert ev.request_id == "req-abc"
    assert ev.resource_id == "F42"
    assert ev.resource_type == "Fund"
    # capture_result defaults to False -- metadata stays empty
    assert ev.metadata == {}
    assert len(store._events) == 1


@pytest.mark.asyncio
async def test_interceptor_records_failure_and_reraises():
    svc, _ = _service()
    interceptor = AuditedInterceptor(svc)

    @Audited("funds.delete", resource_type="Fund", resource_id_from="path:id")
    async def handler():
        raise ValueError("nope")

    req = _request(
        principal=SimpleNamespace(subject="user-9", claims={}),
        path_params={"id": "F1"},
    )
    ctx = _FakeCtx(req, object, handler)

    async def next_call():
        return await handler()

    with pytest.raises(ValueError):
        await interceptor.intercept(ctx, CallHandler(next_call))

    events = await svc.query()
    assert len(events) == 1
    ev = events[0]
    assert ev.outcome == "failure"
    assert ev.resource_id == "F1"
    assert ev.metadata["exception"] == "ValueError"
    assert ev.metadata["message"] == "nope"


@pytest.mark.asyncio
async def test_interceptor_captures_result_when_asked():
    svc, _ = _service()
    interceptor = AuditedInterceptor(svc)

    @Audited("funds.read", resource_type="Fund", capture_result=True)
    async def handler():
        return {"id": "F1", "value": 42}

    req = _request(principal=SimpleNamespace(subject="u", claims={}))
    ctx = _FakeCtx(req, object, handler)

    await interceptor.intercept(ctx, CallHandler(handler))
    ev = (await svc.query())[0]
    assert ev.metadata["result"] == {"id": "F1", "value": 42}


@pytest.mark.asyncio
async def test_interceptor_captures_a_pydantic_result_as_json_safe_primitives():
    """The overwhelmingly common case: a handler returns a response DTO (a pydantic ``BaseModel``,
    often carrying a ``datetime``), not a plain dict. Regression for a real bug: the interceptor
    used to put the raw object straight into ``metadata["result"]``, which round-trips fine through
    ``InMemoryAuditStore`` (no serialization happens) but raised inside SQLAlchemy's JSON bind
    processor for ``OrmAuditStore`` -- a pydantic model / ``datetime`` is not ``json.dumps``-able.
    See ``test_orm_store_persists_a_captured_pydantic_result`` below for the end-to-end proof."""
    from pydantic import BaseModel

    class _FundDto(BaseModel):
        id: str
        decided_at: datetime

    svc, _ = _service()
    interceptor = AuditedInterceptor(svc)
    decided_at = datetime(2026, 1, 1, tzinfo=UTC)

    @Audited("funds.read", resource_type="Fund", capture_result=True)
    async def handler():
        return _FundDto(id="F1", decided_at=decided_at)

    req = _request(principal=SimpleNamespace(subject="u", claims={}))
    ctx = _FakeCtx(req, object, handler)

    await interceptor.intercept(ctx, CallHandler(handler))
    ev = (await svc.query())[0]
    # JSON-safe: a plain dict with the datetime encoded as an ISO string, not the pydantic instance
    # (``jsonable_encoder`` renders UTC as a trailing "Z", not "+00:00" -- both are valid ISO 8601).
    assert ev.metadata["result"] == {"id": "F1", "decided_at": "2026-01-01T00:00:00Z"}


@pytest.mark.asyncio
async def test_orm_store_persists_a_captured_pydantic_result():
    """End-to-end regression proof: capturing a pydantic-model result must not raise when the
    ``AuditLogEntry`` actually reaches a real ``metadata_json`` (SQLAlchemy ``JSON``) column."""
    from pydantic import BaseModel

    from austial.orm import DataSource, SQLiteDriver

    class _FundDto(BaseModel):
        id: str
        decided_at: datetime

    data_source = await DataSource(
        SQLiteDriver("sqlite+aiosqlite:///:memory:"), [AuditLogEntry], synchronize=True
    ).initialize()
    try:
        store = OrmAuditStore(data_source.get_repository(AuditLogEntry))
        svc = AuditLogService(store, AuditConfig(retention_days=1))
        interceptor = AuditedInterceptor(svc)

        @Audited("funds.read", resource_type="Fund", capture_result=True)
        async def handler():
            return _FundDto(id="F1", decided_at=datetime(2026, 1, 1, tzinfo=UTC))

        req = _request(principal=SimpleNamespace(subject="u", claims={}))
        ctx = _FakeCtx(req, object, handler)

        await interceptor.intercept(ctx, CallHandler(handler))  # must not raise StatementError

        rows = await store.query(actor="u")
        assert rows[0].metadata["result"]["id"] == "F1"
    finally:
        await data_source.destroy()


@pytest.mark.asyncio
async def test_interceptor_is_transparent_when_no_metadata():
    svc, _ = _service()
    interceptor = AuditedInterceptor(svc)

    async def handler():
        return {"ok": True}

    ctx = _FakeCtx(_request(), object, handler)
    result = await interceptor.intercept(ctx, CallHandler(handler))
    assert result == {"ok": True}
    assert await svc.query() == []


def test_audited_metadata_is_readable_from_the_handler():
    @Audited("funds.list", resource_type="Fund")
    def handler():
        return []

    spec = get_audit_spec(handler)
    assert spec is not None
    assert spec.action == "funds.list"
    assert spec.resource_type == "Fund"


# ---------------------------------------------------------------------------
# Retention + legal hold


@pytest.mark.asyncio
async def test_evict_older_than_removes_stale_events():
    svc, store = _service()
    from dataclasses import replace

    now = datetime.now(UTC)
    stale = replace(AuditEvent(action="a", resource_type="R"), timestamp=now - timedelta(days=3000))
    fresh = AuditEvent(action="a", resource_type="R")
    await svc.record(stale)
    await svc.record(fresh)

    cutoff = now - timedelta(days=1825)
    evicted = await svc.evict_older_than(cutoff)
    assert evicted == 1
    remaining = await svc.query()
    assert len(remaining) == 1
    assert remaining[0].id == fresh.id


@pytest.mark.asyncio
async def test_legal_hold_preserves_row_across_eviction():
    svc, store = _service()
    from dataclasses import replace

    now = datetime.now(UTC)
    held = replace(AuditEvent(action="kyc.deny", resource_type="Case"), timestamp=now - timedelta(days=3000))
    await svc.record(held)
    store.set_legal_hold(held.id, hold=True)

    evicted = await svc.evict_older_than(now - timedelta(days=1825))
    assert evicted == 0
    still_there = await svc.query()
    assert len(still_there) == 1 and still_there[0].id == held.id


@pytest.mark.asyncio
async def test_evict_expired_uses_configured_retention():
    store = InMemoryAuditStore()
    svc = AuditLogService(store, AuditConfig(retention_days=1))
    from dataclasses import replace

    now = datetime.now(UTC)
    old = replace(AuditEvent(action="a", resource_type="R"), timestamp=now - timedelta(days=5))
    await svc.record(old)
    await svc.record(AuditEvent(action="a", resource_type="R"))

    evicted = await svc.evict_expired(now=now)
    assert evicted == 1


# ---------------------------------------------------------------------------
# OrmAuditStore -- prove we hand an ``AuditLogEntry`` down to the repository,
# and that the entity itself is truly append-only.


class _RepoStub:
    """Minimal ``Repository[AuditLogEntry]`` stand-in for unit tests. Records
    what ``insert`` was called with; hitting a real ``DataSource`` here would
    force a driver / DB connection and add nothing to what we are proving."""

    def __init__(self) -> None:
        self.saved: list[AuditLogEntry] = []

    async def insert(self, entity: AuditLogEntry) -> AuditLogEntry:
        self.saved.append(entity)
        return entity

    async def find(self, options: Any = None) -> list[AuditLogEntry]:
        return list(self.saved)

    async def find_by(self, criteria: dict[str, Any]) -> list[AuditLogEntry]:
        rows = list(self.saved)
        for key, value in criteria.items():
            rows = [r for r in rows if getattr(r, key) == value]
        return rows


@pytest.mark.asyncio
async def test_orm_store_writes_an_audit_log_entry():
    repo = _RepoStub()
    store = OrmAuditStore(repo)
    ev = AuditEvent(
        action="funds.create",
        resource_type="Fund",
        actor="u1",
        resource_id="F1",
        metadata={"k": "v"},
    )
    await store.record(ev)

    assert len(repo.saved) == 1
    entry = repo.saved[0]
    assert isinstance(entry, AuditLogEntry)
    assert entry.id == ev.id
    assert entry.action == "funds.create"
    assert entry.resource_id == "F1"
    assert entry.actor == "u1"
    assert entry.metadata_json == {"k": "v"}
    assert entry.legal_hold is False


@pytest.mark.asyncio
async def test_orm_store_query_translates_rows_back_to_events():
    repo = _RepoStub()
    store = OrmAuditStore(repo)
    await store.record(AuditEvent(action="a", resource_type="R", actor="alice"))
    await store.record(AuditEvent(action="a", resource_type="R", actor="bob"))

    results = await store.query(actor="alice")
    assert len(results) == 1
    assert results[0].actor == "alice"
    assert isinstance(results[0], AuditEvent)


@pytest.mark.asyncio
async def test_audit_log_entry_is_append_only_at_the_orm_layer():
    """The persistent log's WORM guarantee ultimately lives in the ORM: a
    call to ``EntityManager.update()`` against an ``AuditLogEntry`` must
    raise ``AppendOnlyViolationError`` regardless of what the audit store
    does. Prove that on the real ``EntityManager`` -- no driver call is
    ever issued because the guard raises before compilation."""
    from austial.orm.entity_manager import EntityManager

    class _NullDriver:
        # ``EntityManager`` never reaches the driver on this path -- the
        # append-only guard raises first -- but the constructor still
        # requires something callable.
        async def execute_update(self, spec):  # pragma: no cover
            raise AssertionError("driver must not be reached")

    manager = EntityManager(_NullDriver(), catalog=None)  # type: ignore[arg-type]
    with pytest.raises(AppendOnlyViolationError):
        await manager.update(AuditLogEntry, {"id": "x"}, {"action": "tampered"})
    with pytest.raises(AppendOnlyViolationError):
        await manager.delete(AuditLogEntry, {"id": "x"})


# -- error classes ------------------------------------------------------------


def test_audit_error_defaults_to_500():
    from austial.audit import AuditError
    from austial.common.exceptions import HttpException

    with pytest.raises(AuditError) as exc:
        raise AuditError()
    assert isinstance(exc.value, HttpException)
    assert exc.value.status_code == 500
    assert exc.value.get_response()["message"] == "Audit log failure"


def test_audit_error_accepts_custom_message_and_status():
    from austial.audit import AuditError

    with pytest.raises(AuditError) as exc:
        raise AuditError("boom", status_code=502)
    assert exc.value.status_code == 502
    assert exc.value.get_response()["message"] == "boom"
    assert str(exc.value) == "boom"


def test_audit_store_unavailable_error_is_503():
    from austial.audit import AuditError, AuditStoreUnavailableError

    with pytest.raises(AuditStoreUnavailableError) as exc:
        raise AuditStoreUnavailableError()
    assert isinstance(exc.value, AuditError)
    assert exc.value.status_code == 503
    assert exc.value.get_response()["message"] == "Audit store unavailable"

    assert AuditStoreUnavailableError("db down").get_response()["message"] == "db down"


def test_legal_hold_violation_error_is_409_and_carries_count():
    from austial.audit import AuditError, LegalHoldViolationError

    with pytest.raises(LegalHoldViolationError) as exc:
        raise LegalHoldViolationError(3)
    assert isinstance(exc.value, AuditError)
    assert exc.value.status_code == 409
    assert exc.value.count == 3
    assert exc.value.get_response()["message"] == "Eviction refused: 3 record(s) under legal hold"


@pytest.mark.asyncio
async def test_orm_store_round_trips_against_a_real_data_source():
    """The stub above proves the call shape; this proves ``record`` really INSERTs a pre-keyed row on an
    ``append_only`` entity (``save()`` would issue an UPDATE and raise ``AppendOnlyViolationError``)."""
    from austial.orm import DataSource, SQLiteDriver

    data_source = await DataSource(
        SQLiteDriver("sqlite+aiosqlite:///:memory:"), [AuditLogEntry], synchronize=True
    ).initialize()
    store = OrmAuditStore(data_source.get_repository(AuditLogEntry))
    event = AuditEvent(action="funds.create", resource_type="Fund", actor="alice", metadata={"k": "v"})

    await store.record(event)

    rows = await store.query(actor="alice")
    assert [r.id for r in rows] == [event.id]
    assert rows[0].metadata == {"k": "v"}
    await data_source.destroy()
