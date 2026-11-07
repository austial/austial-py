"""HTTP-layer features, end to end through a real (in-process) app: built-in pipes, parameter
helpers, versioning, global prefix, host routing, redirects, SSE, streaming, uploads,
serialization, the timeout interceptor, mapped types and the extra HTTP exceptions."""

from __future__ import annotations

import asyncio
import enum
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import UploadFile
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field, ValidationError

from austial import (
    VERSION_NEUTRAL,
    All,
    AnyFilesInterceptor,
    ArgumentMetadata,
    Body,
    ClassSerializerInterceptor,
    Controller,
    DefaultValuePipe,
    Exclude,
    Expose,
    FileFieldsInterceptor,
    FileInterceptor,
    FilesInterceptor,
    FileTypeValidator,
    Get,
    Header,
    Headers,
    HostParam,
    HttpCode,
    Injectable,
    Ip,
    MaxFileSizeValidator,
    MessageEvent,
    Param,
    ParseArrayPipe,
    ParseBoolPipe,
    ParseEnumPipe,
    ParseFilePipe,
    ParseFloatPipe,
    ParseIntPipe,
    ParseUUIDPipe,
    PipeTransform,
    Post,
    Query,
    Redirect,
    RequestMethod,
    RouteInfo,
    SerializeOptions,
    Session,
    Sse,
    StreamableFile,
    TimeoutInterceptor,
    UploadedFile,
    UploadedFiles,
    UseGuards,
    UseInterceptors,
    UsePipes,
    Version,
    VersioningType,
    apply_decorators,
    create_param_decorator,
)
from austial.common import exceptions as exc
from austial.common.mapped_types import IntersectionType, OmitType, PartialType, PickType
from austial.testing import Test


async def make_client(
    *controllers: type,
    providers: tuple = (),
    configure: Callable[[Any], None] | None = None,
    **client_kwargs: Any,
) -> AsyncClient:
    module = await Test.create_testing_module(controllers=list(controllers), providers=list(providers)).compile()
    app = module.create_austial_application()
    if configure is not None:
        configure(app)
    await app.init()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", **client_kwargs)


# ---------------------------------------------------------------------------------------------
# built-in pipes, attached per parameter
# ---------------------------------------------------------------------------------------------


class Color(enum.StrEnum):
    RED = "red"
    BLUE = "blue"


@Controller("pipes")
class PipesController:
    @Get("int/:id")
    async def by_int(self, id: int = Param("id", ParseIntPipe)):
        return {"id": id, "type": type(id).__name__}

    @Get("page")
    async def page(self, page: int = Query("page", DefaultValuePipe(1), ParseIntPipe)):
        return {"page": page}

    @Get("float/:x")
    async def by_float(self, x: float = Param("x", ParseFloatPipe)):
        return {"x": x}

    @Get("flag")
    async def flag(self, on: bool = Query("on", ParseBoolPipe)):
        return {"on": on}

    @Get("uuid/:id")
    async def by_uuid(self, id: str = Param("id", ParseUUIDPipe(version=4))):
        return {"id": id}

    @Get("color/:c")
    async def by_color(self, c: Color = Param("c", ParseEnumPipe(Color))):
        return {"c": c.value, "is_enum": isinstance(c, Color)}

    @Get("ids")
    async def ids(self, ids: list[int] = Query("ids", ParseArrayPipe(items=int))):
        return {"ids": ids}

    @Get("custom-error/:id")
    async def custom_error(
        self,
        id: int = Param(
            "id", ParseIntPipe(error_http_status_code=422, exception_factory=lambda m: exc.NotFoundException(m))
        ),
    ):
        return {"id": id}


async def test_parse_int_pipe_converts_and_rejects() -> None:
    async with await make_client(PipesController) as client:
        ok = await client.get("/pipes/int/42")
        assert ok.json() == {"id": 42, "type": "int"}

        bad = await client.get("/pipes/int/abc")
        assert bad.status_code == 400
        body = bad.json()
        assert (body["statusCode"], body["error"]) == (400, "Bad Request")
        assert body["message"] == "Validation failed (numeric string is expected)"


async def test_default_value_pipe_then_parse_int_pipe() -> None:
    async with await make_client(PipesController) as client:
        assert (await client.get("/pipes/page")).json() == {"page": 1}
        assert (await client.get("/pipes/page?page=7")).json() == {"page": 7}
        assert (await client.get("/pipes/page?page=x")).status_code == 400


async def test_parse_float_bool_uuid_enum_array() -> None:
    good_uuid = str(uuid.uuid4())
    async with await make_client(PipesController) as client:
        assert (await client.get("/pipes/float/3.5")).json() == {"x": 3.5}
        assert (await client.get("/pipes/float/nope")).status_code == 400

        assert (await client.get("/pipes/flag?on=true")).json() == {"on": True}
        assert (await client.get("/pipes/flag?on=false")).json() == {"on": False}
        assert (await client.get("/pipes/flag?on=maybe")).json()["message"] == (
            "Validation failed (boolean string is expected)"
        )

        assert (await client.get(f"/pipes/uuid/{good_uuid}")).json() == {"id": good_uuid}
        bad_uuid = await client.get("/pipes/uuid/not-a-uuid")
        assert bad_uuid.json()["message"] == "Validation failed (uuid v4 is expected)"
        assert (await client.get(f"/pipes/uuid/{uuid.uuid1()}")).status_code == 400  # wrong version

        assert (await client.get("/pipes/color/red")).json() == {"c": "red", "is_enum": True}
        assert (await client.get("/pipes/color/green")).json()["message"] == (
            "Validation failed (enum string is expected)"
        )

        assert (await client.get("/pipes/ids?ids=1,2,3")).json() == {"ids": [1, 2, 3]}
        assert (await client.get("/pipes/ids?ids=1,x")).status_code == 400


async def test_parse_pipe_custom_exception_factory_wins_over_status_code() -> None:
    async with await make_client(PipesController) as client:
        response = await client.get("/pipes/custom-error/zzz")
    assert response.status_code == 404
    assert response.json()["message"] == "Validation failed (numeric string is expected)"


def test_parse_pipes_directly() -> None:
    meta = ArgumentMetadata(type="param", data="id", metatype=int)
    assert ParseIntPipe().transform("12", meta) == 12
    assert ParseIntPipe().transform("12.9", meta) == 12  # like parseInt
    assert ParseIntPipe().transform(5, meta) == 5
    assert ParseIntPipe(optional=True).transform(None, meta) is None
    with pytest.raises(exc.HttpException):
        ParseIntPipe().transform(None, meta)
    with pytest.raises(exc.HttpException):
        ParseIntPipe().transform(True, meta)
    with pytest.raises(exc.HttpException):
        ParseFloatPipe().transform("inf", meta)
    assert ParseArrayPipe(separator=";").transform("a;b", meta) == ["a", "b"]
    assert ParseArrayPipe().transform("", meta) == []
    assert DefaultValuePipe(9).transform(None, meta) == 9
    assert DefaultValuePipe(9).transform(0, meta) == 0
    assert ParseEnumPipe(Color).transform("blue", meta) is Color.BLUE
    with pytest.raises(TypeError):
        ParseArrayPipe(items="nope")


# ---------------------------------------------------------------------------------------------
# pipe argument metadata + scoped pipes (class resolved from DI, async pipes)
# ---------------------------------------------------------------------------------------------


class _CreateDto(BaseModel):
    name: str


SEEN: list[tuple[str, str | None]] = []


@Injectable()
class RecordingPipe(PipeTransform):
    async def transform(self, value, metadata: ArgumentMetadata):  # async pipes are awaited
        SEEN.append((metadata.type, metadata.data))
        return value


@Controller("meta")
@UsePipes(RecordingPipe)
class MetaController:
    @Post(":id")
    async def create(self, id: int = Param("id"), q: str = Query("q"), dto: _CreateDto = Body()):
        return {"id": id, "q": q, "name": dto.name}


async def test_pipes_receive_argument_kind_and_support_async_and_di() -> None:
    SEEN.clear()
    async with await make_client(MetaController, providers=(RecordingPipe,)) as client:
        response = await client.post("/meta/3?q=x", json={"name": "n"})
    assert response.json() == {"id": 3, "q": "x", "name": "n"}
    assert sorted(SEEN) == [("body", "dto"), ("param", "id"), ("query", "q")]


# ---------------------------------------------------------------------------------------------
# parameter helpers: Ip, HostParam, Session, create_param_decorator, apply_decorators
# ---------------------------------------------------------------------------------------------

CurrentUser = create_param_decorator(lambda key, ctx: ctx.get_request().state.user[key])


class _StateGuard:
    async def can_activate(self, context) -> bool:
        context.get_request().state.user = {"id": 7, "name": "ada"}
        return True


async def _async_factory(data, ctx):
    await asyncio.sleep(0)
    return f"{data}:{ctx.get_request().url.path}"


AsyncData = create_param_decorator(_async_factory)


def Authed():
    return apply_decorators(UseGuards(_StateGuard), Header("X-Authed", "yes"))


@Controller("params")
class ParamsController:
    @Get("ip")
    async def ip(self, ip: str = Ip()):
        return {"ip": ip}

    @Get("me")
    @Authed()
    async def me(self, user_id: int = CurrentUser("id"), name: str = CurrentUser("name")):
        return {"user_id": user_id, "name": name}

    @Get("async")
    async def async_data(self, data: str = AsyncData("hello")):
        return {"data": data}

    @Get("session")
    async def session(self, whole: dict = Session(), user: str = Session("user")):
        return {"whole": whole, "user": user}

    @Get("agent")
    async def agent(self, agent: str = Headers("user-agent")):
        return {"agent": agent}


class _FakeSessionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope["session"] = {"user": "bob"}
        await self.app(scope, receive, send)


async def test_ip_param_and_trust_proxy() -> None:
    async with await make_client(ParamsController) as client:
        assert (await client.get("/params/ip")).json() == {"ip": "127.0.0.1"}

    async with await make_client(ParamsController, configure=lambda app: app.set_trust_proxy()) as client:
        response = await client.get("/params/ip", headers={"X-Forwarded-For": "203.0.113.9"})
        assert response.json() == {"ip": "203.0.113.9"}


async def test_custom_param_decorator_runs_after_guards_and_apply_decorators_bundles() -> None:
    async with await make_client(ParamsController) as client:
        response = await client.get("/params/me")
        assert response.json() == {"user_id": 7, "name": "ada"}
        assert response.headers["x-authed"] == "yes"
        assert (await client.get("/params/async")).json() == {"data": "hello:/params/async"}


async def test_session_param() -> None:
    async with await make_client(ParamsController, configure=lambda app: app.use(_FakeSessionMiddleware)) as client:
        assert (await client.get("/params/session")).json() == {"whole": {"user": "bob"}, "user": "bob"}


# ---------------------------------------------------------------------------------------------
# global prefix, versioning, @All, host routing
# ---------------------------------------------------------------------------------------------


@Controller("cats")
class CatsV1Controller:
    @Get()
    async def list(self):
        return {"v": "default-route"}

    @Get("legacy")
    @Version("1")
    async def legacy(self):
        return {"v": 1}

    @Get("new")
    @Version(["2", "3"])
    async def new(self):
        return {"v": "2-or-3"}

    @Get("everywhere")
    @Version(VERSION_NEUTRAL)
    async def everywhere(self):
        return {"v": "neutral"}


@Controller("health")
class HealthController:
    @Get()
    async def check(self):
        return {"ok": True}

    @Post("ping")
    async def ping(self):
        return {"pong": True}


@Controller("any")
class AnyController:
    @All("thing")
    async def thing(self, request_method: str = Query("m", default="?")):
        return {"ok": True}


async def test_global_prefix_with_excludes() -> None:
    def configure(app):
        app.set_global_prefix("api", exclude=["health", RouteInfo("health/ping", RequestMethod.POST)])

    async with await make_client(CatsV1Controller, HealthController, configure=configure) as client:
        assert (await client.get("/api/cats")).status_code == 200
        assert (await client.get("/cats")).status_code == 404
        assert (await client.get("/health")).json() == {"ok": True}
        assert (await client.post("/health/ping")).json() == {"pong": True}


async def test_uri_versioning_with_default_neutral_and_multiple_versions() -> None:
    def configure(app):
        app.set_global_prefix("api")
        app.enable_versioning(VersioningType.URI, default_version="1")

    async with await make_client(CatsV1Controller, configure=configure) as client:
        assert (await client.get("/api/v1/cats")).json() == {"v": "default-route"}  # default_version applied
        assert (await client.get("/api/v1/cats/legacy")).json() == {"v": 1}
        assert (await client.get("/api/v2/cats/new")).json() == {"v": "2-or-3"}
        assert (await client.get("/api/v3/cats/new")).json() == {"v": "2-or-3"}
        assert (await client.get("/api/v1/cats/new")).status_code == 404
        assert (await client.get("/api/cats/everywhere")).json() == {"v": "neutral"}  # neutral: no segment


async def test_uri_versioning_without_prefix_letter() -> None:
    def configure(app):
        app.enable_versioning(VersioningType.URI, prefix=False)

    async with await make_client(CatsV1Controller, configure=configure) as client:
        assert (await client.get("/1/cats/legacy")).json() == {"v": 1}


@Controller("things", version="1")
class ThingsV1:
    @Get()
    async def get(self):
        return {"served_by": "v1"}


@Controller("things", version="2")
class ThingsV2:
    @Get()
    async def get(self):
        return {"served_by": "v2"}


async def test_header_versioning_dispatches_same_path_by_header() -> None:
    def configure(app):
        app.enable_versioning(VersioningType.HEADER, header="X-API-Version")

    async with await make_client(ThingsV1, ThingsV2, configure=configure) as client:
        assert (await client.get("/things", headers={"X-API-Version": "1"})).json() == {"served_by": "v1"}
        assert (await client.get("/things", headers={"X-API-Version": "2"})).json() == {"served_by": "v2"}
        assert (await client.get("/things", headers={"X-API-Version": "9"})).status_code == 404
        assert (await client.get("/things")).status_code == 404  # no header, no default


async def test_media_type_and_custom_versioning() -> None:
    def media(app):
        app.enable_versioning(VersioningType.MEDIA_TYPE, key="v=", default_version="1")

    async with await make_client(ThingsV1, ThingsV2, configure=media) as client:
        assert (await client.get("/things", headers={"Accept": "application/json;v=2"})).json() == {"served_by": "v2"}
        assert (await client.get("/things")).json() == {"served_by": "v1"}  # falls back to default_version

    def custom(app):
        app.enable_versioning(VersioningType.CUSTOM, extractor=lambda request: request.query_params.get("ver"))

    async with await make_client(ThingsV1, ThingsV2, configure=custom) as client:
        assert (await client.get("/things?ver=2")).json() == {"served_by": "v2"}


async def test_enable_versioning_validates_its_arguments_and_timing() -> None:
    module = await Test.create_testing_module(controllers=[ThingsV1]).compile()
    app = module.create_austial_application()
    with pytest.raises(ValueError, match="header"):
        app.enable_versioning(VersioningType.HEADER)
    with pytest.raises(ValueError, match="extractor"):
        app.enable_versioning(VersioningType.CUSTOM)
    await app.init()
    with pytest.raises(RuntimeError, match="before"):
        app.set_global_prefix("late")


async def test_all_decorator_matches_every_method() -> None:
    async with await make_client(AnyController) as client:
        for method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
            assert (await client.request(method, "/any/thing")).json() == {"ok": True}


@Controller("tenant", host=":account.example.com")
class TenantController:
    @Get()
    async def home(self, account: str = HostParam("account"), params: dict = HostParam()):
        return {"account": account, "params": params}


@Controller("tenant", host="admin.example.com")
class AdminController:
    @Get()
    async def home(self):
        return {"who": "admin"}


async def test_host_routing_captures_params_and_dispatches_by_host() -> None:
    async with await make_client(AdminController, TenantController) as client:
        acme = await client.get("/tenant", headers={"Host": "acme.example.com:8000"})
        assert acme.json() == {"account": "acme", "params": {"account": "acme"}}
        assert (await client.get("/tenant", headers={"Host": "admin.example.com"})).json() == {"who": "admin"}
        assert (await client.get("/tenant", headers={"Host": "other.test"})).status_code == 404


# ---------------------------------------------------------------------------------------------
# redirect, SSE, StreamableFile
# ---------------------------------------------------------------------------------------------


@Controller("go")
class RedirectController:
    @Get("fixed")
    @Redirect("https://example.com/docs", 301)
    async def fixed(self):
        return None

    @Get("dynamic")
    @Redirect("https://example.com/default")
    @Header("X-Trace", "1")
    async def dynamic(self, to: str | None = Query("to")):
        return {"url": to, "status_code": 307} if to else None


async def test_redirect_static_and_dynamic() -> None:
    async with await make_client(RedirectController, follow_redirects=False) as client:
        fixed = await client.get("/go/fixed")
        assert (fixed.status_code, fixed.headers["location"]) == (301, "https://example.com/docs")

        default = await client.get("/go/dynamic")
        assert (default.status_code, default.headers["location"]) == (302, "https://example.com/default")
        assert default.headers["x-trace"] == "1"

        chosen = await client.get("/go/dynamic?to=https://example.com/elsewhere")
        assert (chosen.status_code, chosen.headers["location"]) == (307, "https://example.com/elsewhere")


@Controller("stream")
class StreamController:
    @Sse("events")
    async def events(self):
        yield MessageEvent(data={"n": 1}, id="1", type="tick", retry=3000)
        yield {"data": "two\nlines", "event": "note"}
        yield "plain"

    @Sse("sync")
    def sync_events(self):
        return [{"data": 1}, {"data": 2}]

    @Get("file")
    async def file(self) -> StreamableFile:
        return StreamableFile(b"%PDF-bytes", type="application/pdf", disposition='attachment; filename="r.pdf"')

    @Get("chunks")
    @HttpCode(206)
    async def chunks(self):
        async def gen():
            yield b"ab"
            yield b"cd"

        return StreamableFile(gen(), type="text/plain")


async def test_sse_frames_and_headers() -> None:
    async with await make_client(StreamController) as client:
        response = await client.get("/stream/events")
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        assert response.text == (
            'id: 1\nevent: tick\nretry: 3000\ndata: {"n": 1}\n\nevent: note\ndata: two\ndata: lines\n\ndata: plain\n\n'
        )
        assert (await client.get("/stream/sync")).text == "data: 1\n\ndata: 2\n\n"


async def test_streamable_file_sets_headers_and_streams() -> None:
    async with await make_client(StreamController) as client:
        file = await client.get("/stream/file")
        assert file.content == b"%PDF-bytes"
        assert file.headers["content-type"] == "application/pdf"
        assert file.headers["content-disposition"] == 'attachment; filename="r.pdf"'
        assert file.headers["content-length"] == "10"

        chunks = await client.get("/stream/chunks")
        assert (chunks.status_code, chunks.content) == (206, b"abcd")


def test_streamable_file_from_path_and_stream(tmp_path) -> None:
    path = tmp_path / "data.bin"
    path.write_bytes(b"x" * 100_000)
    from_path = StreamableFile(path)
    assert from_path.length == 100_000
    assert b"".join(from_path.stream()) == b"x" * 100_000  # type: ignore[arg-type]
    with open(path, "rb") as handle:
        assert b"".join(StreamableFile(handle).stream()) == b"x" * 100_000  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------------------
# uploads: UploadedFile(s), ParseFilePipe, file interceptors
# ---------------------------------------------------------------------------------------------


@Controller("upload")
class UploadController:
    @Post("one")
    async def one(
        self,
        file: UploadFile = UploadedFile(
            "file", ParseFilePipe(validators=[MaxFileSizeValidator(10), FileTypeValidator("png")])
        ),
    ):
        return {"name": file.filename, "size": file.size}

    @Post("optional")
    async def optional(
        self, file: UploadFile | None = UploadedFile("file", ParseFilePipe(file_is_required=False), default=None)
    ):
        return {"got": file is not None}

    @Post("many")
    async def many(self, files: list[UploadFile] = UploadedFiles("files", ParseFilePipe())):
        return {"names": [f.filename for f in files]}

    @Post("limited")
    @UseInterceptors(FileInterceptor("avatar", max_size=5, file_filter=lambda req, f: f.filename != "bad.png"))
    async def limited(self, avatar: UploadFile = UploadedFile("avatar")):
        return {"name": avatar.filename}

    @Post("multi")
    @UseInterceptors(FilesInterceptor("docs", max_count=2))
    async def multi(self, docs: list[UploadFile] = UploadedFiles("docs")):
        return {"n": len(docs)}

    @Post("fields")
    @UseInterceptors(FileFieldsInterceptor([{"name": "a", "max_count": 1}, {"name": "b"}]))
    async def fields(self, a: UploadFile = UploadedFile("a"), b: UploadFile = UploadedFile("b")):
        return {"a": a.filename, "b": b.filename}

    @Post("any")
    @UseInterceptors(AnyFilesInterceptor(max_size=3))
    async def any_files(self, x: UploadFile = UploadedFile("x")):
        return {"ok": True}


async def test_parse_file_pipe_validates_size_type_and_required() -> None:
    async with await make_client(UploadController) as client:
        ok = await client.post("/upload/one", files={"file": ("a.png", b"123", "image/png")})
        assert ok.json() == {"name": "a.png", "size": 3}

        too_big = await client.post("/upload/one", files={"file": ("a.png", b"x" * 11, "image/png")})
        assert (too_big.status_code, too_big.json()["message"]) == (
            400,
            "Validation failed (expected size is less than 10)",
        )

        wrong_type = await client.post("/upload/one", files={"file": ("a.txt", b"1", "text/plain")})
        assert wrong_type.json()["message"] == "Validation failed (expected type is png)"

        optional_missing = await client.post("/upload/optional")
        assert optional_missing.json() == {"got": False}

        many = await client.post("/upload/many", files=[("files", ("a", b"1")), ("files", ("b", b"2"))])
        assert many.json() == {"names": ["a", "b"]}


async def test_file_interceptors_enforce_limits() -> None:
    async with await make_client(UploadController) as client:
        assert (await client.post("/upload/limited", files={"avatar": ("ok.png", b"12", "image/png")})).json() == {
            "name": "ok.png"
        }
        big = await client.post("/upload/limited", files={"avatar": ("ok.png", b"123456", "image/png")})
        assert big.status_code == 413
        rejected = await client.post("/upload/limited", files={"avatar": ("bad.png", b"1", "image/png")})
        assert rejected.status_code == 400
        unexpected = await client.post(
            "/upload/limited", files={"avatar": ("ok.png", b"1", "image/png"), "other": ("x", b"1")}
        )
        assert (unexpected.status_code, unexpected.json()["message"]) == (400, "Unexpected field 'other'")

        three = await client.post("/upload/multi", files=[("docs", (f"{i}", b"1")) for i in range(3)])
        assert three.status_code == 400 and "Too many files" in three.json()["message"]
        two = await client.post("/upload/multi", files=[("docs", (f"{i}", b"1")) for i in range(2)])
        assert two.json() == {"n": 2}

        fields = await client.post("/upload/fields", files={"a": ("fa", b"1"), "b": ("fb", b"2")})
        assert fields.json() == {"a": "fa", "b": "fb"}
        two_a = await client.post("/upload/fields", files=[("a", ("1", b"1")), ("a", ("2", b"1")), ("b", ("3", b"1"))])
        assert two_a.status_code == 400

        any_ok = await client.post("/upload/any", files={"x": ("x", b"123")})
        assert any_ok.status_code == 201  # POST default
        any_big = await client.post("/upload/any", files={"x": ("x", b"1234")})
        assert any_big.status_code == 413


# ---------------------------------------------------------------------------------------------
# serialization
# ---------------------------------------------------------------------------------------------


@Exclude("password_hash")
class UserOut(BaseModel):
    id: int
    email: str
    password_hash: str


@Expose("id", "email", groups=None)
@Expose("phone", groups=["admin"])
class Strict(BaseModel):
    id: int
    email: str
    phone: str
    secret: str


@Exclude("internal")
@dataclass
class Item:
    name: str
    internal: str


class Plain:
    def __init__(self) -> None:
        self.visible = 1
        self._private = 2


class Wrapper(BaseModel):
    user: UserOut
    items: list[Item]
    meta: dict[str, UserOut]
    hidden: str = Field(default="x", exclude=True)


@Controller("ser")
@UseInterceptors(ClassSerializerInterceptor())
class SerController:
    @Get("user")
    async def user(self):
        return UserOut(id=1, email="a@b.c", password_hash="secret")

    @Get("nested")
    async def nested(self):
        user = UserOut(id=1, email="a@b.c", password_hash="secret")
        return Wrapper(user=user, items=[Item("i", "x")], meta={"k": user})

    @Get("plain")
    async def plain(self):
        return [Plain(), {"inner": Plain()}, 5, "s", None]

    @Get("public")
    @SerializeOptions(strategy="exclude_all", groups=["public"])
    async def public(self):
        return Strict(id=1, email="e", phone="p", secret="s")

    @Get("admin")
    @SerializeOptions(strategy="exclude_all", groups=["admin"])
    async def admin(self):
        return Strict(id=1, email="e", phone="p", secret="s")


async def test_class_serializer_interceptor() -> None:
    async with await make_client(SerController) as client:
        assert (await client.get("/ser/user")).json() == {"id": 1, "email": "a@b.c"}
        assert (await client.get("/ser/nested")).json() == {
            "user": {"id": 1, "email": "a@b.c"},
            "items": [{"name": "i"}],
            "meta": {"k": {"id": 1, "email": "a@b.c"}},
        }
        assert (await client.get("/ser/plain")).json() == [{"visible": 1}, {"inner": {"visible": 1}}, 5, "s", None]
        assert (await client.get("/ser/public")).json() == {"id": 1, "email": "e"}
        assert (await client.get("/ser/admin")).json() == {"id": 1, "email": "e", "phone": "p"}


# ---------------------------------------------------------------------------------------------
# timeout interceptor
# ---------------------------------------------------------------------------------------------


@Controller("slow")
@UseInterceptors(TimeoutInterceptor(seconds=0.05))
class SlowController:
    @Get("fast")
    async def fast(self):
        return {"ok": True}

    @Get("slow")
    async def slow(self):
        await asyncio.sleep(1)
        return {"ok": True}


async def test_timeout_interceptor_answers_408() -> None:
    async with await make_client(SlowController) as client:
        assert (await client.get("/slow/fast")).status_code == 200
        slow = await client.get("/slow/slow")
        assert (slow.status_code, slow.json()["message"]) == (408, "Request timed out")


# ---------------------------------------------------------------------------------------------
# static assets, compression
# ---------------------------------------------------------------------------------------------


async def test_static_assets_are_mounted_after_api_routes(tmp_path) -> None:
    (tmp_path / "hello.txt").write_text("hi there")
    (tmp_path / "index.html").write_text("<h1>home</h1>")

    def configure(app):
        app.use_static_assets(str(tmp_path), prefix="/", html=True)

    async with await make_client(HealthController, configure=configure) as client:
        assert (await client.get("/hello.txt")).text == "hi there"
        assert "<h1>home</h1>" in (await client.get("/")).text
        assert (await client.get("/health")).json() == {"ok": True}  # API still wins
        assert (await client.get("/missing.txt")).status_code == 404


@Controller("big")
class BigController:
    @Get()
    async def big(self):
        return {"data": "x" * 5000}


async def test_compression() -> None:
    async with await make_client(BigController, configure=lambda app: app.use_compression(minimum_size=100)) as client:
        response = await client.get("/big", headers={"Accept-Encoding": "gzip"})
        assert response.headers["content-encoding"] == "gzip"
        assert response.json() == {"data": "x" * 5000}


# ---------------------------------------------------------------------------------------------
# extra HTTP exceptions
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cls", "status", "phrase"),
    [
        (exc.NotAcceptableException, 406, "Not Acceptable"),
        (exc.RequestTimeoutException, 408, "Request Timeout"),
        (exc.GoneException, 410, "Gone"),
        (exc.PreconditionFailedException, 412, "Precondition Failed"),
        (exc.PayloadTooLargeException, 413, "Payload Too Large"),
        (exc.UnsupportedMediaTypeException, 415, "Unsupported Media Type"),
        (exc.ImATeapotException, 418, "I'm a teapot"),
        (exc.MisdirectedException, 421, "Misdirected"),
        (exc.BadGatewayException, 502, "Bad Gateway"),
        (exc.GatewayTimeoutException, 504, "Gateway Timeout"),
        (exc.HttpVersionNotSupportedException, 505, "HTTP Version Not Supported"),
    ],
)
def test_extra_http_exceptions(cls: type[exc.HttpException], status: int, phrase: str) -> None:
    default = cls()
    assert default.get_status() == status
    assert default.get_response() == {"statusCode": status, "message": phrase, "error": phrase}
    assert cls("custom").get_response()["message"] == "custom"


# ---------------------------------------------------------------------------------------------
# mapped types
# ---------------------------------------------------------------------------------------------


class CreateCatDto(BaseModel):
    name: str = Field(min_length=2)
    age: int
    tags: list[str] = Field(default_factory=list)


class TimestampsDto(BaseModel):
    created_at: str


def test_partial_type_makes_every_field_optional_but_keeps_constraints() -> None:
    Partial = PartialType(CreateCatDto)
    assert Partial().model_dump() == {"name": None, "age": None, "tags": None}
    assert Partial(age=3).model_dump()["age"] == 3
    with pytest.raises(ValidationError):
        Partial(name="x")  # min_length survives


def test_pick_omit_and_intersection() -> None:
    assert set(PickType(CreateCatDto, ["name"]).model_fields) == {"name"}
    assert set(OmitType(CreateCatDto, ["age"]).model_fields) == {"name", "tags"}
    merged = IntersectionType(CreateCatDto, TimestampsDto)
    assert set(merged.model_fields) == {"name", "age", "tags", "created_at"}
    assert merged(name="ab", age=1, created_at="now").model_dump()["created_at"] == "now"
    with pytest.raises(KeyError):
        PickType(CreateCatDto, ["nope"])
    with pytest.raises(KeyError):
        OmitType(CreateCatDto, ["nope"])
    with pytest.raises(TypeError):
        IntersectionType(CreateCatDto)


class UpdateCatDto(PartialType(CreateCatDto)):  # type: ignore[misc]
    pass


@Controller("dto")
class DtoController:
    @Post()
    async def update(self, dto: UpdateCatDto = Body()):
        return dto.model_dump(exclude_none=True)


async def test_mapped_type_works_as_a_request_body_and_in_openapi() -> None:
    module = await Test.create_testing_module(controllers=[DtoController]).compile()
    app = module.create_austial_application()
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/dto", json={"age": 4})).json() == {"age": 4}
        assert (await client.post("/dto", json={"name": "x"})).status_code == 400
        schema = (await client.get("/openapi.json")).json()
    assert "UpdateCatDto" in schema["components"]["schemas"]
