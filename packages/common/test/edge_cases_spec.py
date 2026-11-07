"""Edge cases for the HTTP-layer building blocks (pure units, plus a few routes)."""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import re
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from austial import (
    DefaultValuePipe,
    Exclude,
    Expose,
    FileTypeValidator,
    FileValidator,
    MaxFileSizeValidator,
    MessageEvent,
    ParseArrayPipe,
    ParseBoolPipe,
    ParseEnumPipe,
    ParseFilePipe,
    ParseIntPipe,
    ParseUUIDPipe,
    PartialType,
    PipeTransform,
    StreamableFile,
    ValidationPipe,
    VersioningType,
)
from austial.common import exceptions as exc
from austial.common.pipes.validation_pipe import ArgumentMetadata
from austial.common.serializer import EXCLUDE_ALL, serialize
from austial.common.sse import format_sse
from austial.testing import Test

META = ArgumentMetadata(type="param", data="x", metatype=str)


# ---------------------------------------------------------------------------------------------
# pipes
# ---------------------------------------------------------------------------------------------


def test_validation_pipe_passes_models_and_plain_values_through() -> None:
    class Dto(BaseModel):
        n: int = Field(gt=0)

    pipe = ValidationPipe()
    good = Dto(n=1)
    assert pipe.transform(good, META) is good
    assert pipe.transform("plain", META) == "plain"
    broken = Dto.model_construct(n=-5)  # bypasses validation, like a mutated/constructed instance
    with pytest.raises(exc.BadRequestException) as caught:
        pipe.transform(broken, META)
    assert caught.value.get_response()["error"] == "Bad Request"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("false", False), (True, True), (False, False)],
)
def test_parse_bool_accepts(value, expected) -> None:
    assert ParseBoolPipe().transform(value, META) is expected


@pytest.mark.parametrize("value", ["1", "yes", "TRUE", 1, None])
def test_parse_bool_rejects(value) -> None:
    with pytest.raises(exc.HttpException):
        ParseBoolPipe().transform(value, META)


@pytest.mark.parametrize("value", ["", "  ", "1e", "abc", None, float("nan"), float("inf"), [], {}])
def test_parse_int_rejects_non_numeric(value) -> None:
    with pytest.raises(exc.HttpException) as caught:
        ParseIntPipe().transform(value, META)
    assert caught.value.status_code == 400


def test_parse_int_accepts_large_and_signed_numbers() -> None:
    assert ParseIntPipe().transform("-7", META) == -7
    assert ParseIntPipe().transform("9" * 25, META) == int("9" * 25)  # no float precision loss
    assert ParseIntPipe().transform(" 5 ", META) == 5


def test_parse_uuid_accepts_canonical_only_and_checks_version() -> None:
    v4 = str(uuid.uuid4())
    assert ParseUUIDPipe().transform(v4, META) == v4
    assert ParseUUIDPipe().transform(v4.upper(), META) == v4.upper()
    assert ParseUUIDPipe(version=4).transform(v4, META) == v4
    for bad in (v4.replace("-", ""), f"{{{v4}}}", f"urn:uuid:{v4}", "", None, 5):
        with pytest.raises(exc.HttpException):
            ParseUUIDPipe().transform(bad, META)
    with pytest.raises(exc.HttpException, match="v1"):
        ParseUUIDPipe(version=1).transform(v4, META)


def test_parse_enum_supports_int_enums_and_enum_members() -> None:
    class Level(enum.IntEnum):
        LOW = 1
        HIGH = 2

    assert ParseEnumPipe(Level).transform("2", META) is Level.HIGH
    assert ParseEnumPipe(Level).transform(1, META) is Level.LOW
    assert ParseEnumPipe(Level).transform(Level.LOW, META) is Level.LOW
    with pytest.raises(exc.HttpException):
        ParseEnumPipe(Level).transform("3", META)


def test_parse_array_with_pipe_class_instance_and_list_input() -> None:
    assert ParseArrayPipe(items=ParseIntPipe).transform("1,2", META) == [1, 2]
    assert ParseArrayPipe(items=ParseIntPipe()).transform(["3", "4"], META) == [3, 4]
    assert ParseArrayPipe(items=float).transform("1.5, 2", META) == [1.5, 2.0]
    assert ParseArrayPipe(items=bool).transform("true,false", META) == [True, False]
    assert ParseArrayPipe().transform(("a", "b"), META) == ["a", "b"]
    with pytest.raises(exc.HttpException, match="array"):
        ParseArrayPipe().transform(5, META)
    assert ParseArrayPipe(optional=True).transform(None, META) is None


def test_default_value_pipe_keeps_falsy_values() -> None:
    pipe = DefaultValuePipe("dflt")
    assert pipe.transform("", META) == ""
    assert pipe.transform(0, META) == 0
    assert pipe.transform(False, META) is False
    assert pipe.transform(None, META) == "dflt"


class CustomPipe(PipeTransform):
    def transform(self, value, metadata):
        return value


def test_array_pipe_item_pipe_must_be_a_pipe() -> None:
    assert isinstance(ParseArrayPipe(items=CustomPipe)._item_pipe, CustomPipe)  # noqa: SLF001
    with pytest.raises(TypeError):
        ParseArrayPipe(items=str)


# ---------------------------------------------------------------------------------------------
# file pipes
# ---------------------------------------------------------------------------------------------


def _upload(name="a.png", content=b"12345", content_type="image/png"):
    import io

    stream = io.BytesIO(content)
    return SimpleNamespace(filename=name, file=stream, size=None, content_type=content_type)


def test_max_file_size_falls_back_to_the_stream_when_size_is_unknown() -> None:
    assert MaxFileSizeValidator(5).is_valid(_upload())
    assert not MaxFileSizeValidator(4).is_valid(_upload())
    assert MaxFileSizeValidator(1, message="too big").build_error_message(_upload()) == "too big"


def test_file_type_validator_regex_and_suffix() -> None:
    assert FileTypeValidator(re.compile(r"^image/(png|jpeg)$")).is_valid(_upload())
    assert not FileTypeValidator(re.compile(r"^image/jpeg$")).is_valid(_upload())
    assert not FileTypeValidator("png").is_valid(_upload(content_type=None))
    assert "expected type is" in FileTypeValidator(re.compile("x")).build_error_message(_upload())


def test_parse_file_pipe_custom_validator_status_and_factory() -> None:
    class NotEmpty(FileValidator):
        def is_valid(self, file) -> bool:
            return file.file.read() != b""

        def build_error_message(self, file) -> str:
            return "empty!"

    pipe = ParseFilePipe(validators=[NotEmpty()], error_http_status_code=422)
    with pytest.raises(exc.HttpException) as caught:
        pipe.transform(_upload(content=b""), META)
    assert (caught.value.status_code, caught.value.get_response()["message"]) == (422, "empty!")

    factory_pipe = ParseFilePipe(exception_factory=lambda m: exc.GoneException(m))
    with pytest.raises(exc.GoneException, match="File is required"):
        factory_pipe.transform(None, META)
    with pytest.raises(exc.GoneException):
        factory_pipe.transform([], META)

    assert ParseFilePipe(file_is_required=False).transform(None, META) is None
    # a list of files is validated element by element
    list_pipe = ParseFilePipe(validators=[MaxFileSizeValidator(5)])
    with pytest.raises(exc.HttpException):
        list_pipe.transform([_upload(), _upload(content=b"x" * 9)], META)


# ---------------------------------------------------------------------------------------------
# SSE formatting, StreamableFile
# ---------------------------------------------------------------------------------------------


def test_format_sse_shapes() -> None:
    assert format_sse("hi") == "data: hi\n\n"
    assert format_sse({"a": 1}) == 'data: {"a": 1}\n\n'  # dict without a `data` key is itself the payload
    assert format_sse({"data": 5, "id": 9}) == "id: 9\ndata: 5\n\n"
    assert format_sse(MessageEvent(data="", type="ping")) == "event: ping\ndata: \n\n"
    assert format_sse({"data": "x", "type": "t", "retry": 10}) == "event: t\nretry: 10\ndata: x\n\n"
    assert format_sse(MessageEvent(data=dt.date(2026, 1, 2))) == 'data: "2026-01-02"\n\n'
    assert format_sse(MessageEvent(data=None)) == "data: null\n\n"


def test_streamable_file_headers_and_missing_length() -> None:
    plain = StreamableFile(iter([b"a", b"b"]))
    assert plain.length is None and "Content-Length" not in plain.headers
    assert plain.headers == {"Content-Type": "application/octet-stream"}
    assert b"".join(plain.stream()) == b"ab"  # type: ignore[arg-type]

    explicit = StreamableFile(b"abc", length=99, disposition="inline")
    assert explicit.headers == {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": "inline",
        "Content-Length": "99",
    }
    assert StreamableFile("/definitely/not/here").length is None


# ---------------------------------------------------------------------------------------------
# serialization
# ---------------------------------------------------------------------------------------------


def test_serialize_passes_scalars_enums_and_responses_through() -> None:
    from starlette.responses import Response

    class Color(enum.Enum):
        RED = 1

    response = Response("x")
    assert serialize([1, "a", None, True, b"b", Color.RED, response]) == [1, "a", None, True, b"b", Color.RED, response]
    when = dt.datetime(2026, 1, 1)
    assert serialize({"when": when, "id": uuid.UUID(int=1)}) == {"when": when, "id": uuid.UUID(int=1)}
    assert serialize({1, 2}) in ([1, 2], [2, 1])


def test_exclude_and_expose_are_inherited_and_merge_down_the_mro() -> None:
    @Exclude("secret")
    @dataclasses.dataclass
    class Base:
        id: int
        secret: str

    @Exclude("token")
    @dataclasses.dataclass
    class Child(Base):
        token: str = "t"

    assert serialize(Child(id=1, secret="s", token="t")) == {"id": 1}

    @Expose("id")
    @dataclasses.dataclass
    class OnlyId:
        id: int
        other: int

    assert serialize(OnlyId(1, 2), strategy=EXCLUDE_ALL) == {"id": 1}
    assert serialize(OnlyId(1, 2)) == {"id": 1, "other": 2}


def test_serialize_pydantic_honours_alias_and_field_exclude() -> None:
    class M(BaseModel):
        user_id: int = Field(alias="userId")
        hidden: str = Field(default="x", exclude=True)

    assert serialize(M(userId=3)) == {"userId": 3}


# ---------------------------------------------------------------------------------------------
# mapped types
# ---------------------------------------------------------------------------------------------


def test_partial_type_clears_default_factories_and_preserves_config() -> None:
    class Base(BaseModel):
        model_config = {"extra": "forbid"}
        tags: list[str] = Field(default_factory=list)
        name: str

    partial = PartialType(Base)
    assert partial().model_dump()["tags"] is None
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        partial(unknown=1)  # extra="forbid" carried over


# ---------------------------------------------------------------------------------------------
# routes: regression and edge behaviour through the full stack
# ---------------------------------------------------------------------------------------------


async def _client(*controllers, configure=None):
    module = await Test.create_testing_module(controllers=list(controllers)).compile()
    app = module.create_austial_application()
    if configure:
        configure(app)
    await app.init()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_params_without_pipes_keep_fastapi_coercion() -> None:
    from austial import Controller, Get, Param, Query

    @Controller("plain")
    class PlainController:
        @Get(":id")
        async def get(self, id: int = Param("id"), flag: bool = Query("flag", default=False)):
            return {"id": id, "flag": flag, "types": [type(id).__name__, type(flag).__name__]}

    async with await _client(PlainController) as client:
        assert (await client.get("/plain/5?flag=true")).json() == {"id": 5, "flag": True, "types": ["int", "bool"]}
        assert (await client.get("/plain/x")).status_code == 400  # FastAPI validation, Nest-shaped


async def test_optional_piped_query_param_defaults_to_none() -> None:
    from austial import Controller, Get, Query

    @Controller("opt")
    class OptController:
        @Get()
        async def get(self, n: int | None = Query("n", ParseIntPipe(optional=True))):
            return {"n": n}

    async with await _client(OptController) as client:
        assert (await client.get("/opt")).json() == {"n": None}
        assert (await client.get("/opt?n=4")).json() == {"n": 4}
        assert (await client.get("/opt?n=zz")).status_code == 400


async def test_sync_handlers_pipes_and_deferred_params_work() -> None:
    from austial import Controller, FromRequestState, Get, Param

    @Controller("sync")
    class SyncController:
        @Get(":id")
        def get(self, id: int = Param("id", ParseIntPipe), user=FromRequestState("user", default="anon")):
            return {"id": id, "user": user}

    async with await _client(SyncController) as client:
        assert (await client.get("/sync/3")).json() == {"id": 3, "user": "anon"}


async def test_root_controller_with_global_prefix_and_version() -> None:
    from austial import Controller, Get

    @Controller(version="1")
    class RootController:
        @Get()
        async def root(self):
            return {"root": True}

    def configure(app):
        app.set_global_prefix("api")
        app.enable_versioning(VersioningType.URI)

    async with await _client(RootController, configure=configure) as client:
        assert (await client.get("/api/v1")).json() == {"root": True}


async def test_header_versioning_accepts_comma_separated_values() -> None:
    from austial import Controller, Get

    @Controller("multi", version="2")
    class V2:
        @Get()
        async def get(self):
            return {"v": 2}

    def configure(app):
        app.enable_versioning(VersioningType.HEADER, header="X-V")

    async with await _client(V2, configure=configure) as client:
        assert (await client.get("/multi", headers={"X-V": "1, 2"})).json() == {"v": 2}
        assert (await client.get("/multi", headers={"X-V": "1"})).status_code == 404


async def test_wrong_method_on_versioned_route_is_405_not_404() -> None:
    from austial import Controller, Get

    @Controller("only-get", version="1")
    class OnlyGet:
        @Get()
        async def get(self):
            return {}

    def configure(app):
        app.enable_versioning(VersioningType.HEADER, header="X-V")

    async with await _client(OnlyGet, configure=configure) as client:
        assert (await client.post("/only-get", headers={"X-V": "1"})).status_code == 405


async def test_exception_classes_flow_through_the_pipeline() -> None:
    from austial import Controller, Get

    @Controller("errs")
    class ErrController:
        @Get("gone")
        async def gone(self):
            raise exc.GoneException("it left")

        @Get("custom")
        async def custom(self):
            raise exc.PayloadTooLargeException({"message": ["too big"], "error": "Payload Too Large", "limit": 5})

    async with await _client(ErrController) as client:
        gone = await client.get("/errs/gone")
        assert (gone.status_code, gone.json()["message"]) == (410, "it left")
        custom = await client.get("/errs/custom")
        assert custom.status_code == 413 and custom.json()["limit"] == 5
