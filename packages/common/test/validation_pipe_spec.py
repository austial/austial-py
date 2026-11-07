"""``ValidationPipe`` options: whitelist, forbid_non_whitelisted, stop_at_first_error,
disable_error_messages, error_http_status_code, exception_factory."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict, Field

from austial import Body, Controller, HttpException, Post, UsePipes, ValidationPipe
from austial.common.exceptions import BadRequestException, GoneException
from austial.common.pipes import ArgumentMetadata
from austial.testing import Test

META = ArgumentMetadata(type="body", data="dto", metatype=None)


class Dto(BaseModel):
    name: str = Field(min_length=3)
    age: int = Field(gt=0, alias="userAge")


class OpenDto(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str


def invalid() -> Dto:
    return Dto.model_construct(name="x", userAge=-1)  # bypass parsing to feed the pipe an invalid model


def test_default_behaviour_is_unchanged() -> None:
    with pytest.raises(BadRequestException) as caught:
        ValidationPipe().transform(invalid(), META)
    body = caught.value.get_response()
    assert body["statusCode"] == 400 and body["error"] == "Bad Request" and len(body["message"]) == 2


def test_stop_at_first_error() -> None:
    with pytest.raises(BadRequestException) as caught:
        ValidationPipe(stop_at_first_error=True).transform(invalid(), META)
    assert len(caught.value.get_response()["message"]) == 1


def test_disable_error_messages_hides_the_details() -> None:
    with pytest.raises(HttpException) as caught:
        ValidationPipe(disable_error_messages=True).transform(invalid(), META)
    assert caught.value.get_response() == {"statusCode": 400, "message": "Bad Request", "error": "Bad Request"}


def test_error_http_status_code_and_exception_factory() -> None:
    with pytest.raises(HttpException) as caught:
        ValidationPipe(error_http_status_code=422).transform(invalid(), META)
    assert caught.value.status_code == 422 and len(caught.value.get_response()["message"]) == 2

    seen: list[list[str]] = []

    def factory(errors: list[str]) -> Exception:
        seen.append(errors)
        return GoneException("custom")

    with pytest.raises(GoneException, match="custom"):
        ValidationPipe(exception_factory=factory).transform(invalid(), META)
    assert len(seen[0]) == 2


def test_whitelist_strips_extra_properties_from_open_models() -> None:
    model = OpenDto(name="n", surprise=1)  # type: ignore[call-arg]
    assert model.model_extra == {"surprise": 1}
    assert ValidationPipe().transform(model, META).model_extra == {"surprise": 1}
    assert ValidationPipe(whitelist=True).transform(model, META).model_extra == {}


def test_non_models_pass_through_untouched() -> None:
    for value in ("x", 5, None, [1]):
        assert ValidationPipe(forbid_non_whitelisted=True).transform(value, META) == value


@Controller("strict")
@UsePipes(ValidationPipe(forbid_non_whitelisted=True))
class StrictController:
    @Post()
    async def create(self, dto: Dto = Body()):
        return {"name": dto.name, "age": dto.age}

    @Post("embedded")
    async def embedded(self, dto: Dto = Body(embed=True)):
        return {"name": dto.name}


async def _client() -> AsyncClient:
    module = await Test.create_testing_module(controllers=[StrictController]).compile()
    app = module.create_austial_application()
    await app.init()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_forbid_non_whitelisted_rejects_unknown_top_level_properties() -> None:
    async with await _client() as client:
        ok = await client.post("/strict", json={"name": "abc", "userAge": 3})
        assert ok.json() == {"name": "abc", "age": 3}  # aliases count as known

        bad = await client.post("/strict", json={"name": "abc", "userAge": 3, "role": "admin", "x": 1})
        body = bad.json()
        assert bad.status_code == 400
        assert body["message"] == ["property role should not exist", "property x should not exist"]


async def test_forbid_non_whitelisted_handles_embedded_bodies() -> None:
    async with await _client() as client:
        ok = await client.post("/strict/embedded", json={"dto": {"name": "abc", "userAge": 3}})
        assert ok.json() == {"name": "abc"}
        bad = await client.post("/strict/embedded", json={"dto": {"name": "abc", "userAge": 3, "extra": 1}})
        assert bad.status_code == 400 and bad.json()["message"] == ["property extra should not exist"]


def test_models_with_aliased_fields_validate_cleanly() -> None:
    """Regression: the re-validation used to dump by field name, which an aliased field rejects."""
    good = Dto(name="abc", userAge=3)
    assert ValidationPipe().transform(good, META) is good
