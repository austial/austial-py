"""ParseDatePipe, Cookies, RawBody, @Render and the richer middleware targeting."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.responses import Response

from austial import (
    ArgumentMetadata,
    Controller,
    Cookies,
    Get,
    MiddlewareConsumer,
    Module,
    NestMiddleware,
    ParseDatePipe,
    Post,
    Query,
    RawBody,
    Render,
    RequestMethod,
    Res,
    RouteInfo,
)
from austial.common import exceptions as exc
from austial.common.middleware.base import MiddlewareBinding
from austial.testing import Test

META = ArgumentMetadata(type="query", data="d", metatype=None)


# -- ParseDatePipe -------------------------------------------------------------------------


def test_parse_date_pipe_accepts_iso_dates_datetimes_and_epochs() -> None:
    pipe = ParseDatePipe()
    assert pipe.transform("2026-11-07", META) == datetime(2026, 11, 7, tzinfo=UTC)
    assert pipe.transform("2026-11-07T10:30:00Z", META) == datetime(2026, 11, 7, 10, 30, tzinfo=UTC)
    assert pipe.transform("2026-11-07T10:30:00+05:30", META).utcoffset().total_seconds() == 19800
    assert pipe.transform("2026-11-07T10:30:00", META).tzinfo is UTC  # offset-less -> UTC
    assert pipe.transform("0", META) == datetime(1970, 1, 1, tzinfo=UTC)
    assert pipe.transform(86400, META) == datetime(1970, 1, 2, tzinfo=UTC)
    aware = datetime(2026, 1, 1, tzinfo=UTC)
    assert pipe.transform(aware, META) is aware
    assert pipe.transform(date(2026, 1, 2), META) == datetime(2026, 1, 2, tzinfo=UTC)


def test_parse_date_pipe_date_only_optional_and_failures() -> None:
    assert ParseDatePipe(date_only=True).transform("2026-11-07T23:59:00Z", META) == date(2026, 11, 7)
    assert ParseDatePipe(optional=True).transform(None, META) is None
    bad_values: list[Any] = ["not-a-date", "2026-13-45", "", None, True, [], "99999999999999999999"]
    for bad in bad_values:
        with pytest.raises(exc.HttpException) as caught:
            ParseDatePipe().transform(bad, META)
        assert caught.value.get_response()["message"] == "Validation failed (invalid date format)"


# -- cookies, raw body, render -------------------------------------------------------------


@Controller("web")
class WebController:
    @Get("cookies")
    async def cookies(self, session: str | None = Cookies("session"), everything: dict = Cookies()):
        return {"session": session, "all": everything}

    @Get("login")
    async def login(self, response: Res):
        response.set_cookie("session", "abc123", httponly=True)
        return {"ok": True}

    @Post("webhook")
    async def webhook(self, body: bytes = RawBody()):
        digest = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        return {"length": len(body), "digest": digest}

    @Get("page")
    @Render("page.html")
    async def page(self, name: str = Query("name", default="world")):
        return {"name": name, "items": ["a", "b"]}


async def _client(*controllers, configure=None, providers=()):
    module = await Test.create_testing_module(controllers=list(controllers), providers=list(providers)).compile()
    app = module.create_austial_application()
    if configure:
        configure(app)
    await app.init()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_cookies_param_and_setting_cookies() -> None:
    async with await _client(WebController) as client:
        client.cookies.set("session", "xyz")
        client.cookies.set("theme", "dark")
        body = (await client.get("/web/cookies")).json()
        assert body == {"session": "xyz", "all": {"session": "xyz", "theme": "dark"}}

    async with await _client(WebController) as client:
        assert (await client.get("/web/cookies")).json()["session"] is None
        login = await client.get("/web/login")
        assert "session=abc123" in login.headers["set-cookie"] and "HttpOnly" in login.headers["set-cookie"]


async def test_raw_body_is_the_exact_bytes_even_for_json_requests() -> None:
    payload = b'{"event":  "paid",   "id": 7}'  # odd spacing survives: not re-serialised
    async with await _client(WebController) as client:
        response = await client.post("/web/webhook", content=payload, headers={"content-type": "application/json"})
    assert response.json() == {
        "length": len(payload),
        "digest": hmac.new(b"secret", payload, hashlib.sha256).hexdigest(),
    }


async def test_render_templates(tmp_path: Path) -> None:
    (tmp_path / "page.html").write_text("<h1>Hello {{ name }}</h1>{% for i in items %}<li>{{ i }}</li>{% endfor %}")
    async with await _client(WebController, configure=lambda app: app.set_base_views_dir(str(tmp_path))) as client:
        response = await client.get("/web/page?name=Ada")
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == "<h1>Hello Ada</h1><li>a</li><li>b</li>"


async def test_render_without_a_views_dir_explains_itself() -> None:
    async with await _client(WebController) as client:
        response = await client.get("/web/page")
    assert response.status_code == 500  # the message is logged, never leaked to the client


async def test_set_base_views_dir_must_come_before_init() -> None:
    module = await Test.create_testing_module(controllers=[WebController]).compile()
    app = module.create_austial_application()
    await app.init()
    with pytest.raises(RuntimeError, match="before"):
        app.set_base_views_dir("views")


# -- middleware targeting ------------------------------------------------------------------


@Controller("cats")
class CatsController:
    @Get()
    async def list(self):
        return "cats"

    @Get("secret")
    async def secret(self):
        return "secret"

    @Post()
    async def create(self):
        return "created"


@Controller("dogs")
class DogsController:
    @Get()
    async def list(self):
        return "dogs"


class Mark(NestMiddleware):
    def __init__(self, label: str = "mark"):
        self.label = label

    async def use(self, request, call_next):
        response: Response = await call_next()
        response.headers[f"x-{self.label}"] = "1"
        return response


async def timer(request, call_next):  # a plain function works as middleware
    response = await call_next()
    response.headers["x-timer"] = "1"
    return response


@Module(controllers=[CatsController, DogsController])
class TargetingModule:
    def configure(self, consumer: MiddlewareConsumer) -> None:
        consumer.apply(Mark("cats-only")).for_routes(CatsController)
        consumer.apply(Mark("not-secret")).exclude("cats/secret").for_routes("cats*")
        consumer.apply(Mark("post-only")).for_routes(RouteInfo("cats", RequestMethod.POST))
        consumer.apply(timer).exclude(DogsController).for_routes("*")


async def test_middleware_targets_controllers_routeinfo_exclude_and_functions() -> None:
    from austial import AustialFactory

    app = AustialFactory.create(TargetingModule)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        cats = await client.get("/cats")
        secret = await client.get("/cats/secret")
        dogs = await client.get("/dogs")
        created = await client.post("/cats")

    assert "x-cats-only" in cats.headers and "x-cats-only" in secret.headers and "x-cats-only" not in dogs.headers
    assert "x-not-secret" in cats.headers and "x-not-secret" not in secret.headers  # exclude() wins
    assert "x-post-only" in created.headers and "x-post-only" not in cats.headers  # method-specific
    assert "x-timer" in cats.headers and "x-timer" not in dogs.headers  # function middleware + excluded controller


def test_middleware_binding_path_matching_rules() -> None:
    def hits(routes, path, method="GET", excludes=()):
        return MiddlewareBinding([], routes, excludes).matches(path, method)

    assert hits(["/cats"], "/cats") and hits(["cats"], "/cats/1")
    assert not hits(["/cats"], "/catsup")  # no accidental prefix matches
    assert hits(["/cats*"], "/catsup") and hits(["*"], "/anything") and hits(["(.*)"], "/x")
    assert hits(["/a/b"], "/a/b") and not hits(["/a/b"], "/a")
    assert not hits(["*"], "/health", excludes=["health"])
    assert hits([RouteInfo("x", RequestMethod.POST)], "/x", "POST") and not hits(
        [RouteInfo("x", RequestMethod.POST)], "/x"
    )
    assert hits([RouteInfo("x")], "/x", "DELETE")  # method ALL
    assert hits([CatsController], "/cats/anything") and not hits([CatsController], "/dogs")


def test_apply_rejects_things_that_are_not_middleware() -> None:
    with pytest.raises(TypeError, match="Not a middleware"):
        MiddlewareConsumer().apply(42)
