"""Walks the resolved controller list and builds real ``fastapi.APIRouter``s
out of them, wiring the full Nest-style request pipeline around each handler:

    guards -> pipes -> interceptors (wrapping) -> handler -> exception filters

This is the piece that makes ``@Controller``/``@Get``/``@UseGuards``/etc. do
something, instead of just being inert metadata.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi import params as fastapi_params
from starlette.responses import RedirectResponse, StreamingResponse

from austial.common.decorators.controllers import ControllerMetadata, RouteMetadata
from austial.common.decorators.params import (
    DeferredParam,
    _NextMarker,
    get_param_pipes,
    is_raw_string_param,
    param_kind,
)
from austial.common.enums import VersioningType
from austial.common.exceptions.http_exceptions import ForbiddenException
from austial.common.file.streamable_file import StreamableFile
from austial.common.filters.all_exceptions_filter import AllExceptionsFilter
from austial.common.guards.base import ExecutionContext
from austial.common.interceptors.base import CallHandler
from austial.common.logger import Logger
from austial.common.next import PassToNext
from austial.common.pipes.validation_pipe import ArgumentMetadata
from austial.common.sse import format_sse
from austial.core.container import Container
from austial.core.exception_dispatch import dispatch_exception
from austial.core.metadata import (
    CONTROLLER_METADATA,
    FILTERS_METADATA,
    GUARDS_METADATA,
    HEADER_METADATA,
    HTTP_CODE_METADATA,
    INTERCEPTORS_METADATA,
    OPENAPI_METADATA,
    PIPES_METADATA,
    REDIRECT_METADATA,
    RENDER_METADATA,
    ROUTE_METADATA,
    SSE_METADATA,
    VERSION_METADATA,
    get_metadata,
)
from austial.core.request_context import ContextIdFactory, get_current_context, use_context
from austial.core.routing import (
    GlobalPrefix,
    PassThrough,
    VersioningOptions,
    effective_versions,
    host_matcher,
    route_class_for,
    uri_version_segment,
    version_matcher,
)

_logger = Logger("RoutesResolver")

_REQUEST_PARAM_NAME = "__austial_request__"
_RESPONSE_PARAM_NAME = "__austial_response__"
_DEFAULT_STATUS = {"POST": 201}
_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


def _merge_openapi(controller: dict, handler: dict) -> dict:
    """Controller-level OpenAPI metadata, overridden/extended by the handler's."""
    merged: dict[str, Any] = {}
    for key in ("tags", "security"):
        values = [*controller.get(key, []), *handler.get(key, [])]
        if values:
            merged[key] = list(dict.fromkeys(values)) if key == "tags" else values
    responses = {**controller.get("responses", {}), **handler.get("responses", {})}
    if responses:
        merged["responses"] = responses
    for key in ("summary", "description", "deprecated", "operation_id"):
        if key in handler:
            merged[key] = handler[key]
        elif key in controller:
            merged[key] = controller[key]
    if controller.get("exclude") or handler.get("exclude"):
        merged["exclude"] = True
    return merged


def _openapi_route_kwargs(openapi: dict) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for key in ("summary", "description", "deprecated", "operation_id"):
        if key in openapi:
            kwargs[key] = openapi[key]
    if openapi.get("responses"):
        kwargs["responses"] = openapi["responses"]
    if openapi.get("security"):
        kwargs["openapi_extra"] = {"security": [{name: list(scopes)} for name, scopes in openapi["security"]]}
    if openapi.get("exclude"):
        kwargs["include_in_schema"] = False
    return kwargs


def _current_request() -> Request:
    context = get_current_context()
    assert context is not None and context.request is not None
    return context.request


class _ContainerToken:
    """A global component registered through DI (``{"provide": APP_GUARD, ...}``), by its unique token."""

    __slots__ = ("token",)

    def __init__(self, token: Any) -> None:
        self.token = token


class _ScopedRef:
    """A pipeline component (guard, pipe, interceptor, filter) that depends on request-scoped
    providers: it can't be built at startup, so it's resolved afresh for every request."""

    __slots__ = ("_container", "_token")

    def __init__(self, container: Container, token: Any) -> None:
        self._container = container
        self._token = token

    def get(self) -> Any:
        return self._container.resolve(self._token)


def _materialize(items: list) -> list:
    return [item.get() if isinstance(item, _ScopedRef) else item for item in items]


class RouterBuilder:
    def __init__(
        self,
        container: Container,
        *,
        global_guards: list | None = None,
        global_pipes: list | None = None,
        global_interceptors: list | None = None,
        global_filters: list | None = None,
        global_prefix: GlobalPrefix | None = None,
        versioning: VersioningOptions | None = None,
        views_dir: str | None = None,
    ):
        self._container = container
        # `app.use_global_*()` instances first, then providers registered under APP_GUARD & co.
        self._global_guards = [*(global_guards or []), *self._di_globals("guards")]
        self._global_pipes = [*(global_pipes or []), *self._di_globals("pipes")]
        self._global_interceptors = [*(global_interceptors or []), *self._di_globals("interceptors")]
        self._global_filters = [*(global_filters or []), *self._di_globals("filters")]
        self._global_prefix = global_prefix
        self._versioning = versioning
        self._views_dir = views_dir
        self._templates: Any = None

    def _di_globals(self, kind: str) -> list[_ContainerToken]:
        return [_ContainerToken(token) for token in self._container.global_components(kind)]

    def build(self, controllers: list[type]) -> APIRouter:
        root_router = APIRouter()
        for controller_cls in controllers:
            self._register_controller(root_router, controller_cls)
        return root_router

    def _register_controller(self, root_router: APIRouter, controller_cls: type) -> None:
        controller_meta: ControllerMetadata = get_metadata(CONTROLLER_METADATA, controller_cls) or ControllerMetadata()
        # A controller that depends (even transitively) on a request-scoped provider is itself
        # request-scoped: no instance exists at startup, one is built per request.
        request_bound = self._container.is_request_bound(controller_cls)
        instance = None if request_bound else self._container.resolve(controller_cls)

        for name, member in vars(controller_cls).items():
            if not callable(member):
                continue
            route_meta: RouteMetadata | None = get_metadata(ROUTE_METADATA, member)
            if route_meta is None:
                continue
            self._register_route(root_router, controller_meta, controller_cls, name, member, instance, route_meta)

    def _resolve_item(self, item: Any) -> Any:
        if isinstance(item, _ContainerToken):
            token = item.token
            return (
                _ScopedRef(self._container, token)
                if self._container.is_request_bound(token)
                else (self._container.resolve(token))
            )
        if isinstance(item, type):
            return (
                _ScopedRef(self._container, item)
                if self._container.is_request_bound(item)
                else (self._container.resolve(item))
            )
        return item

    def _resolve_chain(
        self,
        key: str,
        controller_cls: type,
        handler: Callable,
        globals_list: list,
        default: list | None = None,
    ) -> list:
        raw = list(globals_list)
        raw += get_metadata(key, controller_cls, [])
        raw += get_metadata(key, handler, [])
        if not raw and default:
            raw = list(default)
        return [self._resolve_item(item) for item in raw]

    def _paths_for(
        self, controller_meta: ControllerMetadata, route_meta: RouteMetadata, versions: list[str] | None
    ) -> list[str]:
        """Every concrete path a route is mounted at: global prefix + (URI version) + controller + route."""
        base = f"{controller_meta.prefix}{route_meta.path}"
        paths = [base]
        if versions and self._versioning is not None and self._versioning.type == VersioningType.URI:
            paths = [uri_version_segment(v, self._versioning) + base for v in versions]
        if self._global_prefix is not None and self._global_prefix.applies_to(base or "/", route_meta.method):
            paths = [f"/{self._global_prefix.prefix.strip('/')}{p}" for p in paths]
        return [p or "/" for p in paths]

    def _register_route(
        self,
        router: APIRouter,
        controller_meta: ControllerMetadata,
        controller_cls: type,
        name: str,
        member: Callable,
        instance: Any,
        route_meta: RouteMetadata,
    ) -> None:
        guards = self._resolve_chain(GUARDS_METADATA, controller_cls, member, self._global_guards)
        interceptors = self._resolve_chain(INTERCEPTORS_METADATA, controller_cls, member, self._global_interceptors)
        pipes = self._resolve_chain(PIPES_METADATA, controller_cls, member, self._global_pipes)
        # `AllExceptionsFilter` always closes the chain: a scoped filter that doesn't match the exception
        # must fall through to the standard Nest-shaped rendering instead of escaping as a bare exception.
        filters = [
            *self._resolve_chain(FILTERS_METADATA, controller_cls, member, self._global_filters),
            AllExceptionsFilter(),
        ]

        redirect = get_metadata(REDIRECT_METADATA, member)
        is_sse = bool(get_metadata(SSE_METADATA, member))
        render = get_metadata(RENDER_METADATA, member)
        status_code = get_metadata(HTTP_CODE_METADATA, member) or _DEFAULT_STATUS.get(route_meta.method, 200)
        headers_meta = get_metadata(HEADER_METADATA, member, {})

        next_token = object()  # identifies this route if its handler declines with `Next()`
        endpoint, return_annotation = self._build_endpoint(
            controller_cls, name, member, instance, guards, interceptors, pipes, filters, headers_meta,
            redirect=redirect, is_sse=is_sse, status_code=status_code, render=render, next_token=next_token,
        )  # fmt: skip

        versions = effective_versions(
            get_metadata(VERSION_METADATA, member) or controller_meta.version, self._versioning
        )
        matchers = [
            m
            for m in (
                host_matcher(controller_meta.host),
                version_matcher(versions, self._versioning) if self._versioning else None,
            )
            if m is not None
        ]
        methods = _ALL_METHODS if route_meta.method == "ALL" else [route_meta.method]
        raw_return = return_annotation
        skip_response_model = (
            is_sse
            or render is not None
            or redirect is not None
            or (isinstance(raw_return, type) and issubclass(raw_return, StreamableFile))
        )
        extra: dict[str, Any] = {"response_model": None} if skip_response_model else {}
        has_next = any(isinstance(p.default, _NextMarker) for p in inspect.signature(member).parameters.values())
        route_class = route_class_for(matchers, token=next_token if has_next else None)
        if route_class is not None:
            extra["route_class_override"] = route_class
        openapi = _merge_openapi(
            get_metadata(OPENAPI_METADATA, controller_cls, {}), get_metadata(OPENAPI_METADATA, member, {})
        )
        tags = (
            openapi.get("tags")
            or controller_meta.tags
            or [controller_cls.__name__.replace("Controller", "") or controller_cls.__name__]
        )
        extra.update(_openapi_route_kwargs(openapi))

        for index, path in enumerate(self._paths_for(controller_meta, route_meta, versions)):
            kwargs = dict(extra)
            if index:
                kwargs.pop("operation_id", None)  # an operationId must be unique: keep it on the first path only
            router.add_api_route(path, endpoint, methods=methods, status_code=status_code, tags=tags, **kwargs)
            _logger.log(f"Mapped {{{route_meta.method}, {path}}} route", context="RoutesResolver")

    def _render_template(self, template: str, context: Any, status_code: int) -> Response:
        if self._views_dir is None:
            raise RuntimeError("@Render needs a views directory: call app.set_base_views_dir('views') first.")
        from starlette.templating import Jinja2Templates

        if self._templates is None:
            self._templates = Jinja2Templates(directory=self._views_dir)
        return self._templates.TemplateResponse(
            _current_request(), template, context if isinstance(context, dict) else {}, status_code=status_code
        )

    @staticmethod
    def _wrap_interceptor(interceptor, context: ExecutionContext, next_call: Callable):
        async def wrapped():
            return await interceptor.intercept(context, CallHandler(next_call))

        return wrapped

    def _build_endpoint(
        self,
        controller_cls: type,
        name: str,
        member: Callable,
        instance: Any,
        guards: list,
        interceptors: list,
        pipes: list,
        filters: list,
        headers_meta: dict,
        *,
        redirect: dict | None,
        is_sse: bool,
        status_code: int,
        render: str | None = None,
        next_token: object | None = None,
    ) -> tuple[Callable, Any]:
        container = self._container
        full_sig = inspect.signature(member, eval_str=True)
        original_params = list(full_sig.parameters.values())[1:]  # drop `self`
        original_sig = full_sig.replace(parameters=original_params)
        is_coroutine = inspect.iscoroutinefunction(member)

        # Params bound via `FromRequestState(...)`, `Ip()`, `create_param_decorator(...)` etc. are
        # `DeferredParam`s: they read the request as it stands *after* the guard loop below -- FastAPI
        # must never resolve them itself (that would happen before the guards ran), so they are
        # stripped from `new_sig` entirely and injected manually inside `endpoint()`.
        deferred_params: dict[str, DeferredParam] = {
            n: p.default for n, p in original_sig.parameters.items() if isinstance(p.default, DeferredParam)
        }
        # Params carrying their own pipes (`Param("id", ParseIntPipe)`), applied after the scoped ones.
        param_markers: dict[str, Any] = {
            n: p.default
            for n, p in original_sig.parameters.items()
            if isinstance(p.default, fastapi_params.Param | fastapi_params.Body | fastapi_params.File)  # noqa: E501
        }
        param_pipes: dict[str, list] = {
            n: [self._resolve_item(item) for item in get_param_pipes(marker)]
            for n, marker in param_markers.items()
            if get_param_pipes(marker)
        }
        annotations = {n: p.annotation for n, p in original_sig.parameters.items()}

        fastapi_params_list = []
        for n, p in original_sig.parameters.items():
            if n in deferred_params:
                continue
            if n in param_markers and is_raw_string_param(param_markers[n]):
                # Hand FastAPI the raw text: the attached pipes (ParseIntPipe, ...) do the parsing.
                optional = getattr(param_markers[n], "default", ...) is None
                p = p.replace(annotation=(str | None) if optional else str)
            fastapi_params_list.append(p)

        request_param_name = next((n for n, p in original_sig.parameters.items() if p.annotation is Request), None)
        response_param_name = next((n for n, p in original_sig.parameters.items() if p.annotation is Response), None)
        extra_params = []
        if request_param_name is None:
            request_param_name = _REQUEST_PARAM_NAME
            extra_params.append(
                inspect.Parameter(_REQUEST_PARAM_NAME, kind=inspect.Parameter.KEYWORD_ONLY, annotation=Request)
            )
        if response_param_name is None:
            response_param_name = _RESPONSE_PARAM_NAME
            extra_params.append(
                inspect.Parameter(_RESPONSE_PARAM_NAME, kind=inspect.Parameter.KEYWORD_ONLY, annotation=Response)
            )
        new_sig = original_sig.replace(parameters=[*fastapi_params_list, *extra_params])
        skip_pipes = {request_param_name, response_param_name}

        def finalize(result: Any, response: Response) -> Any:
            """Turns Austial-specific return values (redirect, SSE, StreamableFile) into responses."""
            converted: Response | None = None
            if render is not None:
                converted = self._render_template(render, result, status_code)
            elif redirect is not None:
                target = dict(redirect)
                if isinstance(result, dict) and "url" in result:
                    target.update({k: result[k] for k in ("url", "status_code") if k in result})
                converted = RedirectResponse(target["url"], status_code=target["status_code"])
            elif is_sse:
                converted = StreamingResponse(
                    _sse_frames(result),
                    status_code=status_code,
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
                )
            elif isinstance(result, StreamableFile):
                stream_headers = {k: v for k, v in result.headers.items() if k != "Content-Type"}
                converted = StreamingResponse(
                    result.stream(), status_code=status_code, media_type=result.type, headers=stream_headers
                )
            if converted is None:
                for key, value in headers_meta.items():
                    response.headers[key] = value
                return result
            for key, value in headers_meta.items():
                converted.headers[key] = value
            return converted

        async def run(request: Request, response: Response, kwargs: dict[str, Any]) -> Any:
            active_filters = _materialize(filters)
            try:
                target_instance = instance if instance is not None else container.resolve(controller_cls)
                handler = getattr(target_instance, name)
                context = ExecutionContext(request, controller_cls, handler, response)

                for guard in _materialize(guards):
                    if not await guard.can_activate(context):
                        raise ForbiddenException("Forbidden resource")

                scoped_pipes = _materialize(pipes)
                for arg_name, value in list(kwargs.items()):
                    if arg_name in skip_pipes:
                        continue
                    marker = param_markers.get(arg_name)
                    annotation = annotations.get(arg_name)
                    metadata = ArgumentMetadata(
                        type=param_kind(marker) if marker is not None else "custom",  # type: ignore[arg-type]
                        data=arg_name,
                        metatype=annotation if isinstance(annotation, type) else type(value),
                        request=request,
                    )
                    for pipe in [*scoped_pipes, *_materialize(param_pipes.get(arg_name, []))]:
                        value = pipe.transform(value, metadata)
                        if inspect.isawaitable(value):
                            value = await value
                    kwargs[arg_name] = value

                # Populated only now, after every guard above has had the chance to write to
                # `request.state` -- see `deferred_params`'s construction above.
                for arg_name, deferred in deferred_params.items():
                    kwargs[arg_name] = await deferred.resolve(context)

                async def call_handler():
                    return await handler(**kwargs) if is_coroutine else handler(**kwargs)

                chain = call_handler
                for interceptor in reversed(_materialize(interceptors)):
                    chain = self._wrap_interceptor(interceptor, context, chain)

                return finalize(await chain(), response)
            except PassToNext:
                # `next()`: let the router offer the request to the next matching route
                return PassThrough(next_token, await request.body())
            except Exception as exc:  # noqa: BLE001 - dispatched to exception filters below
                return await dispatch_exception(exc, request, active_filters)

        async def endpoint(**kwargs):
            request: Request = (
                kwargs.pop(_REQUEST_PARAM_NAME)
                if request_param_name == _REQUEST_PARAM_NAME
                else kwargs[request_param_name]
            )
            response: Response = (
                kwargs.pop(_RESPONSE_PARAM_NAME)
                if response_param_name == _RESPONSE_PARAM_NAME
                else kwargs[response_param_name]
            )
            # Everything below -- guards, pipes, the handler, filters -- resolves request-scoped
            # providers against this request's context.
            with use_context(ContextIdFactory.get_by_request(request)):
                return await run(request, response, kwargs)

        endpoint.__signature__ = new_sig  # type: ignore[attr-defined]  # FastAPI reads this to build the OpenAPI schema
        endpoint.__name__ = getattr(member, "__name__", "endpoint")
        return endpoint, original_sig.return_annotation


async def _sse_frames(source: Any):
    if hasattr(source, "__aiter__"):
        async for event in source:
            yield format_sse(event)
    else:
        for event in source:
            yield format_sse(event)
