"""End-to-end test -- mirrors a Nest ``*.e2e-spec.ts`` test: spin up a real
(in-process) app via ``austial.testing`` + ``httpx``'s ASGI transport, and hit
routes exactly like a client would, no mocking of the HTTP layer at all.

This is a framework-level test, so the "app" under test (``WidgetsController``
/ ``WidgetsService`` / ``ApiKeyGuard``) is defined right here instead of being
imported from a consumer project -- it exists purely to exercise the full
request lifecycle (guards -> handler -> exception filters) end to end.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from austial import (
    Body,
    CanActivate,
    Controller,
    ExecutionContext,
    Get,
    Injectable,
    NotFoundException,
    Post,
    UseGuards,
)
from austial.testing import Test


class Widget(BaseModel):
    id: int
    name: str


class CreateWidgetDto(BaseModel):
    name: str


@Injectable()
class WidgetsService:
    def __init__(self) -> None:
        self._items: list[Widget] = []
        self._next_id = 1

    def create(self, dto: CreateWidgetDto) -> Widget:
        widget = Widget(id=self._next_id, name=dto.name)
        self._next_id += 1
        self._items.append(widget)
        return widget

    def find_all(self) -> list[Widget]:
        return self._items

    def find_one(self, id: int) -> Widget:
        for item in self._items:
            if item.id == id:
                return item
        raise NotFoundException(f"Widget #{id} not found")


class ApiKeyGuard(CanActivate):
    async def can_activate(self, context: ExecutionContext) -> bool:
        request = context.switch_to_http().get_request()
        return request.headers.get("x-api-key") == "test-key"


@Controller("widgets")
class WidgetsController:
    def __init__(self, service: WidgetsService):
        self.service = service

    @Post()
    async def create(self, dto: CreateWidgetDto = Body()) -> Widget:
        return self.service.create(dto)

    @Get()
    @UseGuards(ApiKeyGuard)
    async def find_all(self) -> list[Widget]:
        return self.service.find_all()

    @Get(":id")
    async def find_one(self, id: int) -> Widget:
        return self.service.find_one(id)


async def _make_client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_full_request_lifecycle_guard_and_handler():
    module = await Test.create_testing_module(controllers=[WidgetsController], providers=[WidgetsService]).compile()
    app = module.create_austial_application()
    await app.init()

    async with await _make_client(app) as client:
        create_response = await client.post("/widgets", json={"name": "Gizmo"})
        assert create_response.status_code == 201
        widget_id = create_response.json()["id"]

        denied = await client.get("/widgets")
        assert denied.status_code == 403

        allowed = await client.get("/widgets", headers={"x-api-key": "test-key"})
        assert allowed.status_code == 200
        assert len(allowed.json()) == 1

        get_one = await client.get(f"/widgets/{widget_id}")
        assert get_one.status_code == 200
        assert get_one.json()["name"] == "Gizmo"


@pytest.mark.asyncio
async def test_not_found_returns_nest_shaped_error():
    module = await Test.create_testing_module(controllers=[WidgetsController], providers=[WidgetsService]).compile()
    app = module.create_austial_application()
    await app.init()

    async with await _make_client(app) as client:
        response = await client.get("/widgets/999")
        assert response.status_code == 404
        body = response.json()
        assert body["statusCode"] == 404
        assert "timestamp" in body
        assert body["path"] == "/widgets/999"
