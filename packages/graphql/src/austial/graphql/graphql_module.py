"""``GraphQLModule.for_root(...)`` -- mounts a Strawberry schema, mirrors ``@nestjs/graphql`` (code-first style).

Austial doesn't generate a schema from decorated classes the way Nest does; Strawberry already does that well. What this
module adds is the framework integration: the schema is served by the application (at ``path``), and resolvers reach
dependency injection through the request context::

    import strawberry
    from austial.graphql import GraphQLModule, inject

    @strawberry.type
    class Query:
        @strawberry.field
        def greeting(self, info: strawberry.Info, name: str) -> str:
            return inject(info, GreetingService).greet(name)       # a normal provider

    schema = strawberry.Schema(query=Query)

    @Module(imports=[GraphQLModule.for_root(schema=schema)], providers=[GreetingService])
    class AppModule: ...

``schema`` may also be a callable ``(module_ref) -> strawberry.Schema``, for schemas built from providers.
Needs ``pip install 'austial-graphql[strawberry]'``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Response
from starlette.requests import HTTPConnection

from austial.common.decorators.injectable import Inject
from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule
from austial.core.http_adapter_host import HttpAdapterHost
from austial.core.module_ref import ModuleRef
from austial.core.request_context import ContextId, ContextIdFactory

GRAPHQL_OPTIONS = "AUSTIAL_GRAPHQL_OPTIONS"


class GraphQLOptions:
    def __init__(
        self,
        schema: Any,
        path: str,
        ide: str | None,
        context_getter: Callable[..., Any] | None,
        allow_queries_via_get: bool,
    ):
        self.schema = schema
        self.path = path
        self.ide = ide
        self.context_getter = context_getter
        self.allow_queries_via_get = allow_queries_via_get


class GraphQLMount:
    """Mounts the router when the application bootstraps."""

    def __init__(
        self,
        host: HttpAdapterHost,
        module_ref: ModuleRef,
        options: GraphQLOptions = Inject(GRAPHQL_OPTIONS),
    ):
        self.options, self.host, self.module_ref = options, host, module_ref

    def on_application_bootstrap(self) -> None:
        try:
            from strawberry.fastapi import GraphQLRouter
        except ImportError as exc:
            raise RuntimeError(
                "GraphQLModule needs Strawberry with FastAPI support: pip install 'austial-graphql[strawberry]'"
            ) from exc
        if self.host.http_adapter is None:
            return
        schema = self.options.schema
        if callable(schema) and not hasattr(schema, "execute"):
            schema = schema(self.module_ref)
        module_ref, extra_context = self.module_ref, self.options.context_getter

        async def get_context(request: HTTPConnection, response: Response) -> dict[str, Any]:
            # HTTPConnection covers both POST/GET requests and subscription WebSockets.
            context_id = ContextIdFactory.get_by_request(request)
            context: dict[str, Any] = {
                "request": request,
                "response": response,
                "module_ref": module_ref,
                "context_id": context_id,
            }
            if extra_context is not None:
                extra = extra_context(request)
                if hasattr(extra, "__await__"):
                    extra = await extra
                context.update(extra or {})
            return context

        router = GraphQLRouter(
            schema,
            path=self.options.path,
            graphql_ide=self.options.ide,  # type: ignore[arg-type]  # validated by Strawberry itself
            allow_queries_via_get=self.options.allow_queries_via_get,
            context_getter=get_context,
        )
        self.host.http_adapter.include_router(router)


def inject(info: Any, token: Any) -> Any:
    """Resolve a provider from inside a resolver: ``inject(info, CatsService)``. Request-scoped providers are built
    once per GraphQL request."""
    context = info.context
    context_id: ContextId = context["context_id"]
    return context["module_ref"].resolve(token, context_id)


@Module()
class GraphQLModule:
    @staticmethod
    def for_root(
        *,
        schema: Any,
        path: str = "/graphql",
        ide: str | None = "graphiql",
        context_getter: Callable[..., Any] | None = None,
        allow_queries_via_get: bool = True,
    ) -> DynamicModule:
        """``ide``: ``"graphiql"``, ``"apollo-sandbox"``, ``"pathfinder"`` or ``None`` to disable the browser UI.
        ``context_getter(request)`` may add entries (the authenticated user, ...) to every resolver's context."""
        options = GraphQLOptions(schema, path, ide, context_getter, allow_queries_via_get)
        return DynamicModule(
            module=GraphQLModule,
            providers=[{"provide": GRAPHQL_OPTIONS, "useValue": options}, GraphQLMount],
        )
