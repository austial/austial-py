"""The HTTP-layer features, live: real uvicorn, real sockets, real httpx."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel, Field

from austial import (
    AustialFactory,
    Body,
    CanActivate,
    Catch,
    Controller,
    Cookies,
    ExceptionFilter,
    ExecutionContext,
    Get,
    Header,
    Headers,
    HttpCode,
    Injectable,
    MessageEvent,
    Module,
    NestInterceptor,
    Next,
    Param,
    ParseIntPipe,
    Post,
    Query,
    RawBody,
    Redirect,
    Render,
    Res,
    Sse,
    UseFilters,
    UseGuards,
    UseInterceptors,
    Version,
    VersioningType,
)
from austial.common.exceptions import ForbiddenException, NotFoundException
from integration.live import serve

HERE = Path(__file__).parent
SECRET = b"whsec"


class Tag(NestInterceptor):
    async def intercept(self, context, next):
        return {"data": await next.handle()}


class Gate(CanActivate):
    async def can_activate(self, context: ExecutionContext) -> bool:
        if context.get_request().headers.get("x-token") != "ok":
            raise ForbiddenException("no token")
        return True


@Catch(NotFoundException)
class Teapot(ExceptionFilter):
    async def catch(self, exc, host):
        from fastapi.responses import JSONResponse

        return JSONResponse({"teapot": True}, status_code=418)


class CreateCat(BaseModel):
    name: str = Field(min_length=2)
    age: int = Field(ge=0)


@Injectable()
class Cats:
    def __init__(self) -> None:
        self.items: list[dict] = []


@Controller("cats", version="1")
class CatsV1:
    def __init__(self, cats: Cats):
        self.cats = cats

    @Post()
    @HttpCode(201)
    def create(self, dto: CreateCat = Body()):
        self.cats.items.append(dto.model_dump())
        return dto

    @Get()
    @UseInterceptors(Tag)
    def all(self):
        return self.cats.items

    @Get("search")
    @Version("2")
    def search(self):
        return {"v": 2}

    @Get("guarded")
    @UseGuards(Gate)
    def guarded(self):
        return {"in": True}

    @Get(":id")
    @UseFilters(Teapot)
    def one(self, id: int = Param("id", ParseIntPipe)):
        if id >= len(self.cats.items):
            raise NotFoundException("no cat")
        return self.cats.items[id]


@Controller("files")
class CacheFirst:
    @Get(":name")
    async def cached(self, name: str = Param("name"), next=Next()):
        return {"from": "cache"} if name == "hot" else next()


@Controller("files")
class Origin:
    @Get(":name")
    async def origin(self, name: str = Param("name")):
        return {"from": "origin", "name": name}


@Controller("misc")
class Misc:
    @Get("cookie")
    def cookie(self, response: Res, session: str | None = Cookies("session")):
        response.set_cookie("seen", "1")
        return {"session": session}

    @Post("webhook")
    async def webhook(self, body: bytes = RawBody(), signature: str = Headers("x-signature")):
        expected = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        return {"valid": hmac.compare_digest(expected, signature), "bytes": len(body)}

    @Get("go")
    @Redirect("/misc/target", 302)
    def go(self):
        return None

    @Get("target")
    def target(self):
        return {"arrived": True}

    @Get("headers")
    @Header("X-Custom", "yes")
    def headers(self):
        return {"ok": True}

    @Sse("ticks")
    async def ticks(self):
        for n in range(3):
            yield MessageEvent(data={"tick": n}, id=str(n), type="tick")

    @Get("big")
    def big(self):
        return {"text": "x" * 5000}


@Controller()
class Pages:
    @Get("page")
    @Render("index.html")
    def page(self, name: str = Query("name", default="world")):
        return {"name": name, "items": ["a", "b"]}


@Controller("health")
class Health:
    @Get()
    def health(self):
        return {"ok": True}


@Module(controllers=[CatsV1, CacheFirst, Origin, Misc, Pages, Health], providers=[Cats])
class App:
    pass


def build():
    app = AustialFactory.create(App)
    app.set_global_prefix("api", exclude=["health"])
    app.enable_versioning(VersioningType.URI)
    app.use_compression()
    app.set_base_views_dir(str(HERE / "views"))
    app.use_static_assets(str(HERE / "static"), prefix="/assets")
    return app


async def test_http_features_over_real_sockets() -> None:
    async with serve(build()) as base, httpx.AsyncClient(base_url=base, follow_redirects=False) as c:
        # global prefix + URI versioning + validation + status codes + interceptors
        created = await c.post("/api/v1/cats", json={"name": "tom", "age": 3})
        assert created.status_code == 201 and created.json() == {"name": "tom", "age": 3}
        assert (await c.post("/api/v1/cats", json={"name": "x", "age": -1})).status_code in (400, 422)
        assert (await c.get("/api/v1/cats")).json() == {"data": [{"name": "tom", "age": 3}]}
        assert (await c.get("/api/v2/cats/search")).json() == {"v": 2}
        assert (await c.get("/api/cats")).status_code == 404  # unversioned path is not served
        assert (await c.get("/health")).json() == {"ok": True}  # excluded from the prefix

        # pipes, filters, guards
        assert (await c.get("/api/v1/cats/0")).json() == {"name": "tom", "age": 3}
        assert (await c.get("/api/v1/cats/abc")).status_code in (400, 422)
        missing = await c.get("/api/v1/cats/9")
        assert missing.status_code == 418 and missing.json() == {"teapot": True}
        assert (await c.get("/api/v1/cats/guarded")).status_code == 403
        assert (await c.get("/api/v1/cats/guarded", headers={"x-token": "ok"})).json() == {"in": True}

        # @Next falls through to the next matching route
        assert (await c.get("/api/files/hot")).json() == {"from": "cache"}
        assert (await c.get("/api/files/cold")).json() == {"from": "origin", "name": "cold"}

        # cookies, raw body, redirect, headers
        cookie = await c.get("/api/misc/cookie", cookies={"session": "abc"})
        assert cookie.json() == {"session": "abc"} and "seen=1" in cookie.headers["set-cookie"]
        body = b'{"event":"paid"}'
        signature = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        signed = await c.post("/api/misc/webhook", content=body, headers={"x-signature": signature})
        assert signed.json() == {"valid": True, "bytes": len(body)}
        bad = await c.post("/api/misc/webhook", content=body, headers={"x-signature": "0" * 64})
        assert bad.json()["valid"] is False
        redirected = await c.get("/api/misc/go")
        assert redirected.status_code == 302 and redirected.headers["location"] == "/misc/target"
        assert (await c.get("/api/misc/headers")).headers["x-custom"] == "yes"

        # server-sent events
        async with c.stream("GET", "/api/misc/ticks") as stream:
            assert stream.headers["content-type"].startswith("text/event-stream")
            text = "".join([chunk async for chunk in stream.aiter_text()])
        assert text.count("event: tick") == 3 and 'data: {"tick": 2}' in text

        # templates, static files, compression
        page = await c.get("/api/page", params={"name": "Ada"})
        assert page.headers["content-type"].startswith("text/html") and "<h1>Hello Ada</h1>" in page.text
        assert "<li>a</li><li>b</li>" in page.text
        assert (await c.get("/assets/site.css")).text.strip() == "body{color:red}"
        big = await c.get("/api/misc/big", headers={"accept-encoding": "gzip"})
        assert big.headers.get("content-encoding") == "gzip" and big.json()["text"] == "x" * 5000


async def test_concurrent_requests_and_graceful_shutdown() -> None:
    async with serve(build()) as base, httpx.AsyncClient(base_url=base) as c:
        replies = await asyncio.gather(*(c.get(f"/api/files/n{i}") for i in range(50)))
        assert [r.json()["name"] for r in replies] == [f"n{i}" for i in range(50)]
    with pytest.raises(httpx.ConnectError):  # the server really stopped
        async with httpx.AsyncClient(base_url=base) as c2:
            await c2.get("/health")
