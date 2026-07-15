"""Walks the resolved controller list and builds real ``fastapi.APIRouter``s
out of them, wiring the full Nest-style request pipeline around each handler:

    guards -> pipes -> interceptors (wrapping) -> handler -> exception filters

This is the piece that makes ``@Controller``/``@Get``/``@UseGuards``/etc. do
something, instead of just being inert metadata.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

from fastapi import APIRouter, Request, Response

from austial.common.decorators.controllers import ControllerMetadata, RouteMetadata
from austial.common.exceptions.http_exceptions import ForbiddenException
from austial.common.filters.all_exceptions_filter import AllExceptionsFilter
from austial.common.guards.base import ExecutionContext
from austial.common.interceptors.base import CallHandler
from austial.common.logger import Logger
from austial.common.pipes.validation_pipe import ArgumentMetadata
from austial.core.container import Container
from austial.core.exception_dispatch import dispatch_exception
from austial.core.metadata import (
    CONTROLLER_METADATA,
    FILTERS_METADATA,
    GUARDS_METADATA,
    HEADER_METADATA,
    HTTP_CODE_METADATA,
    INTERCEPTORS_METADATA,
    PIPES_METADATA,
    ROUTE_METADATA,
    get_metadata,
)

_logger = Logger("RoutesResolver")

_REQUEST_PARAM_NAME = "__austial_request__"
_RESPONSE_PARAM_NAME = "__austial_response__"
_DEFAULT_STATUS = {"POST": 201}


class RouterBuilder:
    def __init__(
        self,
        container: Container,
        *,
        global_guards: list | None = None,
        global_pipes: list | None = None,
        global_interceptors: list | None = None,
        global_filters: list | None = None,
    ):
        self._container = container
        self._global_guards = global_guards or []
        self._global_pipes = global_pipes or []
        self._global_interceptors = global_interceptors or []
        self._global_filters = global_filters or []

    def build(self, controllers: list[type]) -> APIRouter:
        root_router = APIRouter()
        for controller_cls in controllers:
            self._register_controller(root_router, controller_cls)
        return root_router

    def _register_controller(self, root_router: APIRouter, controller_cls: type) -> None:
        controller_meta: ControllerMetadata = get_metadata(CONTROLLER_METADATA, controller_cls) or ControllerMetadata()
        instance = self._container.resolve(controller_cls)
        tags = controller_meta.tags or [controller_cls.__name__.replace("Controller", "") or controller_cls.__name__]
        router = APIRouter(prefix=controller_meta.prefix, tags=tags)

        for name, member in vars(controller_cls).items():
            if not callable(member):
                continue
            route_meta: RouteMetadata | None = get_metadata(ROUTE_METADATA, member)
            if route_meta is None:
                continue
            bound_handler = getattr(instance, name)
            self._register_route(router, controller_meta, controller_cls, bound_handler, route_meta)
            full_path = f"{controller_meta.prefix}{route_meta.path}" or "/"
            _logger.log(f"Mapped {{{route_meta.method}, {full_path}}} route", context="RoutesResolver")

        root_router.include_router(router)

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
        resolved = []
        for item in raw:
            resolved.append(self._container.resolve(item) if isinstance(item, type) else item)
        return resolved

    def _register_route(
        self,
        router: APIRouter,
        controller_meta: ControllerMetadata,
        controller_cls: type,
        handler: Callable,
        route_meta: RouteMetadata,
    ) -> None:
        guards = self._resolve_chain(GUARDS_METADATA, controller_cls, handler, self._global_guards)
        interceptors = self._resolve_chain(INTERCEPTORS_METADATA, controller_cls, handler, self._global_interceptors)
        pipes = self._resolve_chain(PIPES_METADATA, controller_cls, handler, self._global_pipes)
        filters = self._resolve_chain(
            FILTERS_METADATA, controller_cls, handler, self._global_filters, default=[AllExceptionsFilter()]
        )

        status_code = get_metadata(HTTP_CODE_METADATA, handler) or _DEFAULT_STATUS.get(route_meta.method, 200)
        headers_meta = get_metadata(HEADER_METADATA, handler, {})

        endpoint = self._build_endpoint(controller_cls, handler, guards, interceptors, pipes, filters, headers_meta)

        path = route_meta.path or ("/" if not controller_meta.prefix else "")
        router.add_api_route(path, endpoint, methods=[route_meta.method], status_code=status_code)

    @staticmethod
    def _wrap_interceptor(interceptor, context: ExecutionContext, next_call: Callable):
        async def wrapped():
            return await interceptor.intercept(context, CallHandler(next_call))

        return wrapped

    def _build_endpoint(
        self,
        controller_cls: type,
        handler: Callable,
        guards: list,
        interceptors: list,
        pipes: list,
        filters: list,
        headers_meta: dict,
    ) -> Callable:
        original_sig = inspect.signature(handler)  # bound method -> `self` already excluded
        request_param = inspect.Parameter(_REQUEST_PARAM_NAME, kind=inspect.Parameter.KEYWORD_ONLY, annotation=Request)
        response_param = inspect.Parameter(
            _RESPONSE_PARAM_NAME, kind=inspect.Parameter.KEYWORD_ONLY, annotation=Response
        )
        new_sig = original_sig.replace(parameters=[*original_sig.parameters.values(), request_param, response_param])
        is_coroutine = inspect.iscoroutinefunction(handler)

        async def endpoint(**kwargs):
            request: Request = kwargs.pop(_REQUEST_PARAM_NAME)
            response: Response = kwargs.pop(_RESPONSE_PARAM_NAME)
            context = ExecutionContext(request, controller_cls, handler)

            try:
                for guard in guards:
                    if not await guard.can_activate(context):
                        raise ForbiddenException("Forbidden resource")

                for name, value in list(kwargs.items()):
                    metadata = ArgumentMetadata(type="custom", data=name, metatype=type(value))
                    for pipe in pipes:
                        value = pipe.transform(value, metadata)
                    kwargs[name] = value

                async def call_handler():
                    return await handler(**kwargs) if is_coroutine else handler(**kwargs)

                chain = call_handler
                for interceptor in reversed(interceptors):
                    chain = self._wrap_interceptor(interceptor, context, chain)

                result = await chain()
                for key, value in headers_meta.items():
                    response.headers[key] = value
                return result
            except Exception as exc:  # noqa: BLE001 - dispatched to exception filters below
                return await dispatch_exception(exc, request, filters)

        endpoint.__signature__ = new_sig  # type: ignore[attr-defined]  # FastAPI reads this to build the OpenAPI schema
        endpoint.__name__ = getattr(handler, "__name__", "endpoint")
        return endpoint
