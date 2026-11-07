"""``Next()``: a handler declines and the request falls through to the next matching route."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from austial import Controller, Get, Headers, Next, Param, Post, UseInterceptors
from austial.testing import Test

CALLS: list[str] = []


class Tag:
    async def intercept(self, context, next):
        CALLS.append("interceptor")
        return await next.handle()


@Controller("files")
class CacheFirst:
    @Get(":name")
    @UseInterceptors(Tag)
    async def cached(self, name: str = Param("name"), next=Next()):
        CALLS.append("cache")
        if name != "hot":
            return next()  # decline: not in the cache
        return {"from": "cache"}


@Controller("files")
class Mirror:
    @Get("cold")
    async def cold(self, x_skip: str | None = Headers("x-skip"), next=Next()):
        CALLS.append("mirror")
        if x_skip:
            next()  # declines too (a bare call also works; it raises)
        return {"from": "mirror"}


@Controller("files")
class Origin:
    @Get(":name")
    async def origin(self, name: str = Param("name")):
        CALLS.append("origin")
        return {"from": "origin", "name": name}


@Controller("posts")
class OnlyPost:
    @Post()
    async def create(self, next=Next()):
        return next()


async def client(*controllers):
    module = await Test.create_testing_module(controllers=list(controllers), providers=[Tag]).compile()
    app = module.create_austial_application()
    await app.init()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_declining_falls_through_to_the_next_matching_route() -> None:
    CALLS.clear()
    async with await client(CacheFirst, Origin) as c:
        assert (await c.get("/files/hot")).json() == {"from": "cache"}
        assert (await c.get("/files/other")).json() == {"from": "origin", "name": "other"}
    assert CALLS == ["interceptor", "cache", "interceptor", "cache", "origin"]  # the declining route ran its pipeline


async def test_chain_of_declines_and_exhaustion_is_a_404() -> None:
    CALLS.clear()
    async with await client(Mirror, CacheFirst) as c:
        # /files/cold: Mirror runs first and answers
        assert (await c.get("/files/cold")).json() == {"from": "mirror"}
        # Mirror declines (header), CacheFirst declines (not "hot"), nothing left -> 404
        declined = await c.get("/files/cold", headers={"x-skip": "1"})
        assert declined.status_code == 404
    assert CALLS == ["mirror", "mirror", "interceptor", "cache"]


async def test_no_further_route_for_the_method_is_404_not_500() -> None:
    async with await client(OnlyPost) as c:
        assert (await c.post("/posts")).status_code == 404


async def test_routes_without_next_are_untouched() -> None:
    async with await client(Origin) as c:
        assert (await c.get("/files/x")).json()["from"] == "origin"
        assert (await c.get("/nope")).status_code == 404
