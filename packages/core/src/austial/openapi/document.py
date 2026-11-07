"""``DocumentBuilder`` and ``SwaggerModule`` -- mirror ``@nestjs/swagger``.

::

    config = (
        DocumentBuilder()
        .set_title("Cats API").set_description("The cats API").set_version("1.0")
        .add_bearer_auth().add_server("https://api.example.com").add_tag("cats", "Everything about cats")
        .build()
    )
    SwaggerModule.setup(app, config, path="api-docs")          # UI at /api-docs, JSON at /api-docs-json
    document = SwaggerModule.create_document(app, config)       # the schema as a dict (after app.init())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OpenApiConfig:
    title: str = "Austial"
    description: str = ""
    version: str = "1.0.0"
    terms_of_service: str | None = None
    contact: dict[str, str] | None = None
    license: dict[str, str] | None = None
    servers: list[dict[str, str]] = field(default_factory=list)
    tags: list[dict[str, str]] = field(default_factory=list)
    security_schemes: dict[str, dict[str, Any]] = field(default_factory=dict)


class DocumentBuilder:
    def __init__(self) -> None:
        self._config = OpenApiConfig()

    def set_title(self, title: str) -> DocumentBuilder:
        self._config.title = title
        return self

    def set_description(self, description: str) -> DocumentBuilder:
        self._config.description = description
        return self

    def set_version(self, version: str) -> DocumentBuilder:
        self._config.version = version
        return self

    def set_terms_of_service(self, url: str) -> DocumentBuilder:
        self._config.terms_of_service = url
        return self

    def set_contact(self, name: str, url: str = "", email: str = "") -> DocumentBuilder:
        self._config.contact = {k: v for k, v in {"name": name, "url": url, "email": email}.items() if v}
        return self

    def set_license(self, name: str, url: str = "") -> DocumentBuilder:
        self._config.license = {k: v for k, v in {"name": name, "url": url}.items() if v}
        return self

    def add_server(self, url: str, description: str = "") -> DocumentBuilder:
        self._config.servers.append({"url": url, **({"description": description} if description else {})})
        return self

    def add_tag(self, name: str, description: str = "") -> DocumentBuilder:
        self._config.tags.append({"name": name, **({"description": description} if description else {})})
        return self

    def add_bearer_auth(self, name: str = "bearer", bearer_format: str = "JWT") -> DocumentBuilder:
        self._config.security_schemes[name] = {"type": "http", "scheme": "bearer", "bearerFormat": bearer_format}
        return self

    def add_basic_auth(self, name: str = "basic") -> DocumentBuilder:
        self._config.security_schemes[name] = {"type": "http", "scheme": "basic"}
        return self

    def add_api_key(
        self, name: str = "api_key", header: str = "X-API-Key", location: str = "header"
    ) -> DocumentBuilder:
        self._config.security_schemes[name] = {"type": "apiKey", "in": location, "name": header}
        return self

    def add_oauth2(self, name: str, flows: dict[str, Any]) -> DocumentBuilder:
        self._config.security_schemes[name] = {"type": "oauth2", "flows": flows}
        return self

    def build(self) -> OpenApiConfig:
        return self._config


def _fastapi_of(app: Any) -> Any:
    return app.get_http_adapter() if hasattr(app, "get_http_adapter") else app


class SwaggerModule:
    @staticmethod
    def _apply(fastapi_app: Any, config: OpenApiConfig) -> None:
        fastapi_app.title = config.title
        fastapi_app.description = config.description
        fastapi_app.version = config.version
        fastapi_app.terms_of_service = config.terms_of_service
        fastapi_app.contact = config.contact
        fastapi_app.license_info = config.license
        fastapi_app.servers = config.servers or None
        fastapi_app.openapi_tags = config.tags or None
        original = fastapi_app.openapi

        def openapi() -> dict[str, Any]:
            if fastapi_app.openapi_schema is None:
                schema = original()
                if config.security_schemes:
                    schema.setdefault("components", {}).setdefault("securitySchemes", {}).update(
                        config.security_schemes
                    )
                fastapi_app.openapi_schema = schema
            return fastapi_app.openapi_schema

        fastapi_app.openapi = openapi
        fastapi_app.openapi_schema = None

    @staticmethod
    def create_document(app: Any, config: OpenApiConfig) -> dict[str, Any]:
        """The OpenAPI document as a dict. Call after ``await app.init()`` (routes must exist)."""
        fastapi_app = _fastapi_of(app)
        if hasattr(app, "_build_routes"):
            app._build_routes()  # noqa: SLF001 - idempotent; makes this usable before the first request
        SwaggerModule._apply(fastapi_app, config)
        return fastapi_app.openapi()

    @staticmethod
    def setup(app: Any, config: OpenApiConfig, path: str = "docs", *, redoc: bool = False) -> None:
        """Serves interactive docs at ``/<path>`` (Swagger UI, or ReDoc with ``redoc=True``) and the schema at
        ``/<path>-json``. FastAPI's built-in ``/docs`` and ``/redoc`` keep working alongside."""
        from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
        from starlette.responses import HTMLResponse, JSONResponse

        fastapi_app = _fastapi_of(app)
        SwaggerModule._apply(fastapi_app, config)
        base = "/" + path.strip("/")
        json_url = f"{base}-json"

        async def schema() -> JSONResponse:
            return JSONResponse(fastapi_app.openapi())

        async def ui() -> HTMLResponse:
            if redoc:
                return get_redoc_html(openapi_url=json_url, title=config.title)
            return get_swagger_ui_html(openapi_url=json_url, title=config.title)

        fastapi_app.add_api_route(json_url, schema, include_in_schema=False)
        fastapi_app.add_api_route(base, ui, include_in_schema=False)
