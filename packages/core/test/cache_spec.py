from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from austial import APP_INTERCEPTOR, Controller, Get, Injectable, Module, Post, Query, UseInterceptors
from austial.cache import (
    CacheInterceptor,
    CacheKey,
    CacheModule,
    CacheOptions,
    CacheService,
    CacheStore,
    CacheTTL,
    MemoryCacheStore,
)
from austial.testing import Test


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


# ---------------------------------------------------------------------------------------------
# MemoryCacheStore
# ---------------------------------------------------------------------------------------------


async def test_store_get_set_delete_clear() -> None:
    store = MemoryCacheStore()
    assert await store.get("a") is None
    await store.set("a", 1)
    await store.set("b", [2])
    assert (await store.get("a"), await store.get("b")) == (1, [2])
    await store.delete("a")
    assert await store.get("a") is None
    await store.clear()
    assert len(store) == 0


async def test_store_entries_expire_by_ttl() -> None:
    clock = FakeClock()
    store = MemoryCacheStore(clock=clock)
    await store.set("k", "v", ttl=10)
    await store.set("forever", "v", ttl=None)
    await store.set("zero-means-forever", "v", ttl=0)
    clock.now = 9.9
    assert await store.get("k") == "v"
    clock.now = 10
    assert await store.get("k") is None
    assert await store.get("forever") == "v" and await store.get("zero-means-forever") == "v"


async def test_store_evicts_least_recently_used() -> None:
    store = MemoryCacheStore(max_items=2)
    await store.set("a", 1)
    await store.set("b", 2)
    await store.get("a")  # a is now the most recently used
    await store.set("c", 3)
    assert await store.get("b") is None  # b was the LRU
    assert (await store.get("a"), await store.get("c")) == (1, 3)
    with pytest.raises(ValueError):
        MemoryCacheStore(max_items=0)


# ---------------------------------------------------------------------------------------------
# CacheService
# ---------------------------------------------------------------------------------------------


async def _service(**options) -> CacheService:
    module = await Test.create_testing_module(imports=[CacheModule.register(**options)]).compile()
    return module.get(CacheService)


async def test_service_uses_default_ttl_and_explicit_ttl() -> None:
    clock = FakeClock()
    service = CacheService(CacheOptions(ttl=5, store=MemoryCacheStore(clock=clock)))
    await service.set("default", 1)
    await service.set("long", 2, ttl=100)
    clock.now = 6
    assert await service.get("default") is None
    assert await service.get("long") == 2
    assert service.default_ttl == 5


async def test_wrap_computes_once_and_shares_concurrent_misses() -> None:
    service = await _service(ttl=60)
    calls = 0

    async def compute() -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return "value"

    results = await asyncio.gather(*(service.wrap("k", compute) for _ in range(5)))
    assert results == ["value"] * 5 and calls == 1  # no stampede
    assert await service.wrap("k", compute) == "value" and calls == 1  # now a plain hit


async def test_wrap_supports_sync_factories_and_propagates_errors_without_caching() -> None:
    service = await _service()
    assert await service.wrap("sync", lambda: 42) == 42

    attempts = 0

    async def flaky() -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("boom")
        return 7

    with pytest.raises(RuntimeError):
        await service.wrap("flaky", flaky)
    assert await service.wrap("flaky", flaky) == 7  # the failure wasn't cached; retried


async def test_custom_store_and_async_registration() -> None:
    class DictStore(CacheStore):
        def __init__(self) -> None:
            self.data: dict = {}

        async def get(self, key):
            return self.data.get(key)

        async def set(self, key, value, ttl=None):
            self.data[key] = value

        async def delete(self, key):
            self.data.pop(key, None)

        async def clear(self):
            self.data.clear()

    store = DictStore()
    module = await Test.create_testing_module(
        imports=[CacheModule.register_async(use_factory=lambda: CacheOptions(store=store))]
    ).compile()
    await module.get(CacheService).set("x", 1)
    assert store.data == {"x": 1}


# ---------------------------------------------------------------------------------------------
# CacheInterceptor
# ---------------------------------------------------------------------------------------------

HITS = {"list": 0, "ttl": 0, "keyed": 0, "post": 0}


@Controller("cats")
@UseInterceptors(CacheInterceptor)
class CatsController:
    @Get()
    async def find_all(self, page: int = Query("page", default=1)):
        HITS["list"] += 1
        return {"page": page, "n": HITS["list"]}

    @Get("short")
    @CacheTTL(1)
    async def short(self):
        HITS["ttl"] += 1
        return HITS["ttl"]

    @Get("featured")
    @CacheKey("featured-cats")
    async def featured(self):
        HITS["keyed"] += 1
        return HITS["keyed"]

    @Post()
    async def create(self):
        HITS["post"] += 1
        return HITS["post"]


async def _client(clock: FakeClock | None = None) -> tuple[AsyncClient, CacheService]:
    options: dict[str, Any] = {"ttl": 60}
    if clock is not None:
        options["store"] = MemoryCacheStore(clock=clock)
    module = await Test.create_testing_module(
        controllers=[CatsController], imports=[CacheModule.register(**options)]
    ).compile()
    app = module.create_austial_application()
    await app.init()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), module.get(CacheService)


async def test_interceptor_caches_get_responses_per_url() -> None:
    HITS.update(list=0)
    client, _ = await _client()
    async with client:
        first = (await client.get("/cats?page=1")).json()
        again = (await client.get("/cats?page=1")).json()
        other_page = (await client.get("/cats?page=2")).json()
    assert first == again == {"page": 1, "n": 1}  # served from cache the second time
    assert other_page == {"page": 2, "n": 2}  # a different query string is a different key
    assert HITS["list"] == 2


async def test_interceptor_never_caches_non_get_requests() -> None:
    HITS.update(post=0)
    client, _ = await _client()
    async with client:
        assert (await client.post("/cats")).json() == 1
        assert (await client.post("/cats")).json() == 2


async def test_cache_key_and_ttl_decorators() -> None:
    HITS.update(ttl=0, keyed=0)
    clock = FakeClock()
    client, cache = await _client(clock)
    async with client:
        assert (await client.get("/cats/featured")).json() == 1
        assert (await client.get("/cats/featured")).json() == 1
        assert await cache.get("featured-cats") == 1  # stored under the explicit key
        await cache.delete("featured-cats")  # invalidate by name
        assert (await client.get("/cats/featured")).json() == 2

        assert (await client.get("/cats/short")).json() == 1
        clock.now = 2  # past the 1s @CacheTTL
        assert (await client.get("/cats/short")).json() == 2


async def test_cache_interceptor_as_a_global_app_interceptor_and_skips_responses() -> None:
    from starlette.responses import PlainTextResponse

    calls = {"n": 0}

    @Controller("g")
    class GlobalController:
        @Get("data")
        async def data(self):
            calls["n"] += 1
            return calls["n"]

        @Get("raw")
        async def raw(self):
            calls["n"] += 1
            return PlainTextResponse(f"raw-{calls['n']}")

        @Get("none")
        async def none(self):
            calls["n"] += 1
            return None

    @Module(
        controllers=[GlobalController],
        providers=[{"provide": APP_INTERCEPTOR, "useClass": CacheInterceptor}],
        imports=[CacheModule.register()],
    )
    class Root:
        pass

    from austial import AustialFactory

    app = AustialFactory.create(Root)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/g/data")).json() == (await client.get("/g/data")).json() == 1
        assert (await client.get("/g/raw")).text == "raw-2"
        assert (await client.get("/g/raw")).text == "raw-3"  # Response objects aren't cached
        await client.get("/g/none")
        await client.get("/g/none")
        assert calls["n"] == 5  # None isn't cached either


async def test_track_by_can_be_overridden_per_user() -> None:
    class PerUser(CacheInterceptor):
        def track_by(self, context):
            base = super().track_by(context)
            return None if base is None else f"{context.get_request().headers.get('x-user', 'anon')}:{base}"

    calls = {"n": 0}

    @Injectable()
    class Counting:
        pass

    @Controller("u")
    @UseInterceptors(PerUser)
    class UserController:
        @Get()
        async def get(self):
            calls["n"] += 1
            return calls["n"]

    module = await Test.create_testing_module(
        controllers=[UserController], providers=[PerUser, Counting], imports=[CacheModule.register()]
    ).compile()
    app = module.create_austial_application()
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        a1 = (await client.get("/u", headers={"x-user": "a"})).json()
        a2 = (await client.get("/u", headers={"x-user": "a"})).json()
        b1 = (await client.get("/u", headers={"x-user": "b"})).json()
    assert a1 == a2 == 1 and b1 == 2
