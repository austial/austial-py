from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from austial import Controller, Get, Post
from austial.openapi import (
    ApiBearerAuth,
    ApiCreatedResponse,
    ApiExcludeController,
    ApiExcludeEndpoint,
    ApiNotFoundResponse,
    ApiOkResponse,
    ApiOperation,
    ApiProperty,
    ApiPropertyOptional,
    ApiResponse,
    ApiSecurity,
    ApiTags,
    DocumentBuilder,
    SwaggerModule,
)
from austial.testing import Test


class Cat(BaseModel):
    name: str = ApiProperty(description="The cat's name", example="Tom", min_length=1)
    age: int | None = ApiPropertyOptional(minimum=0, maximum=40)


class Problem(BaseModel):
    message: str


@ApiTags("cats", "pets")
@ApiBearerAuth()
@Controller("cats")
class CatsController:
    @Get(":id")
    @ApiOperation(summary="Find one cat", description="Looks a cat up by id.", operation_id="findCat")
    @ApiOkResponse("The cat", model=Cat)
    @ApiNotFoundResponse(model=Problem)
    async def find_one(self, id: int) -> Cat:
        return Cat(name="Tom", age=3)

    @Post()
    @ApiCreatedResponse("Created it")
    @ApiOperation(summary="Create", deprecated=True)
    @ApiTags("write")
    async def create(self, cat: Cat) -> Cat:
        return cat

    @Get()
    @ApiExcludeEndpoint()
    async def hidden(self):
        return []


@ApiExcludeController()
@Controller("internal")
class InternalController:
    @Get()
    async def get(self):
        return "x"


@Controller("plain")
class PlainController:
    @Get()
    @ApiSecurity("oauth", ["read", "write"])
    @ApiResponse(418, "Teapot")
    async def get(self):
        return "x"


async def schema(configure=None) -> dict:
    module = await Test.create_testing_module(
        controllers=[CatsController, InternalController, PlainController]
    ).compile()
    app = module.create_austial_application()
    if configure:
        configure(app)
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return (await client.get("/openapi.json")).json()


async def test_decorators_shape_the_generated_operations() -> None:
    doc = await schema()
    find = doc["paths"]["/cats/{id}"]["get"]
    assert find["summary"] == "Find one cat" and find["description"] == "Looks a cat up by id."
    assert find["operationId"] == "findCat"
    assert find["tags"] == ["cats", "pets"]  # from the controller
    assert find["security"] == [{"bearer": []}]
    assert find["responses"]["200"]["description"] == "The cat"
    assert find["responses"]["404"]["description"] == "Not Found"
    assert find["responses"]["404"]["content"]["application/json"]["schema"]["$ref"].endswith("/Problem")

    create = doc["paths"]["/cats"]["post"]
    assert create["deprecated"] is True and create["summary"] == "Create"
    assert create["tags"] == ["cats", "pets", "write"]  # route tags add to the controller's
    assert create["responses"]["201"]["description"] == "Created it"

    assert "get" not in doc["paths"]["/cats"]  # @ApiExcludeEndpoint
    assert "/internal" not in doc["paths"]  # @ApiExcludeController
    plain = doc["paths"]["/plain"]["get"]
    assert plain["security"] == [{"oauth": ["read", "write"]}] and plain["responses"]["418"]["description"] == "Teapot"
    assert plain["tags"] == ["Plain"]  # default tag when none declared


async def test_api_property_documents_model_fields() -> None:
    doc = await schema()
    cat = doc["components"]["schemas"]["Cat"]["properties"]
    assert cat["name"]["description"] == "The cat's name" and cat["name"]["examples"] == ["Tom"]
    assert cat["name"]["minLength"] == 1
    assert any(branch.get("minimum") == 0 and branch.get("maximum") == 40 for branch in cat["age"]["anyOf"]) or (
        cat["age"].get("minimum") == 0 and cat["age"].get("maximum") == 40
    )


async def test_document_builder_and_swagger_setup() -> None:
    config = (
        DocumentBuilder()
        .set_title("Cats API")
        .set_description("All about cats")
        .set_version("2.1")
        .set_terms_of_service("https://example.com/tos")
        .set_contact("Ada", "https://example.com", "ada@example.com")
        .set_license("MIT", "https://opensource.org/licenses/MIT")
        .add_server("https://api.example.com", "production")
        .add_tag("cats", "Everything about cats")
        .add_bearer_auth()
        .add_basic_auth()
        .add_api_key("key", "X-Key")
        .add_oauth2("oauth", {"clientCredentials": {"tokenUrl": "https://x/token", "scopes": {"read": "Read"}}})
        .build()
    )
    module = await Test.create_testing_module(controllers=[CatsController]).compile()
    app = module.create_austial_application()
    SwaggerModule.setup(app, config, path="api-docs")
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        doc = (await client.get("/api-docs-json")).json()
        ui = await client.get("/api-docs")
        default = (await client.get("/openapi.json")).json()
    assert doc["info"]["title"] == "Cats API" and doc["info"]["version"] == "2.1"
    assert doc["info"]["contact"] == {"name": "Ada", "url": "https://example.com/", "email": "ada@example.com"}
    assert doc["info"]["license"]["name"] == "MIT" and doc["info"]["termsOfService"] == "https://example.com/tos"
    assert doc["servers"] == [{"url": "https://api.example.com", "description": "production"}]
    assert doc["tags"] == [{"name": "cats", "description": "Everything about cats"}]
    schemes = doc["components"]["securitySchemes"]
    assert schemes["bearer"] == {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    assert (
        schemes["basic"]["scheme"] == "basic"
        and schemes["key"]["name"] == "X-Key"
        and schemes["oauth"]["type"] == "oauth2"
    )
    assert "swagger" in ui.text.lower() and "/api-docs-json" in ui.text
    assert default["info"]["title"] == "Cats API"  # the built-in /openapi.json reflects the config too
    assert "/api-docs" not in doc["paths"] and "/api-docs-json" not in doc["paths"]


async def test_redoc_and_create_document() -> None:
    module = await Test.create_testing_module(controllers=[CatsController]).compile()
    app = module.create_austial_application()
    config = DocumentBuilder().set_title("T").build()
    SwaggerModule.setup(app, config, path="/reference/", redoc=True)
    document = SwaggerModule.create_document(app, config)  # works before init(): builds the routes itself
    assert document["info"]["title"] == "T" and "/cats/{id}" in document["paths"]
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert "redoc" in (await client.get("/reference")).text.lower()
