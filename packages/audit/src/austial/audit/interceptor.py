"""``AuditedInterceptor`` -- records a success/failure event around the handler.

Reads the :class:`AuditSpec` metadata off the handler (or the controller
class as a fallback), invokes the next call, and records:

- On success: ``outcome="success"``, ``resource_id`` extracted per the
  spec (``result.<path>`` reaches into the response, ``path:<name>``
  reads ``request.path_params``), optional response snapshot in
  ``metadata['result']`` when ``capture_result=True``.
- On exception: ``outcome="failure"``, the exception class name in
  ``metadata['exception']`` and its str form in ``metadata['message']``,
  then re-raises so the framework's exception filter still runs.

Actor/tenant/request-id are read from ``request.state`` -- the interceptor
never re-parses tokens, headers, or cookies. It relies on ``AuthGuard``
(sets ``request.state.user``), ``TenantGuard`` (populates
``request.state.tenant`` when the module is wired) and
``LoggingMiddleware`` (sets ``request.state.request_id``) having already
run. Missing state -> those fields are ``None``, and the event is still
recorded.
"""

from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder

from austial.audit.decorators import AuditSpec, get_audit_spec
from austial.audit.service import AuditLogService
from austial.common.decorators.injectable import Injectable
from austial.common.guards.base import ExecutionContext
from austial.common.interceptors.base import CallHandler, NestInterceptor


def _resolve_resource_id(spec: AuditSpec, request: Any, result: Any) -> str | None:
    """Extract a ``resource_id`` per ``spec.resource_id_from``. Any
    resolution failure (missing key, non-dict response, etc.) returns
    ``None`` -- an audit event without a resource id is still recorded
    rather than dropped or crashed on."""
    source = spec.resource_id_from
    if source is None:
        # Product-supplied override lives on request.state
        return getattr(getattr(request, "state", None), "audit_resource_id", None)

    if source.startswith("path:"):
        param = source[len("path:") :]
        path_params = getattr(request, "path_params", {}) or {}
        value = path_params.get(param)
        return str(value) if value is not None else None

    if source.startswith("result."):
        key_path = source[len("result.") :]
        cursor: Any = result
        for part in key_path.split("."):
            if cursor is None:
                return None
            cursor = cursor.get(part) if isinstance(cursor, dict) else getattr(cursor, part, None)
        return str(cursor) if cursor is not None else None

    return None


def _actor(request: Any) -> str | None:
    principal = getattr(getattr(request, "state", None), "user", None)
    if principal is None:
        return None
    subject = getattr(principal, "subject", None)
    return str(subject) if subject is not None else None


def _tenant(request: Any) -> str | None:
    tenant = getattr(getattr(request, "state", None), "tenant", None)
    if tenant is None:
        return None
    if isinstance(tenant, str):
        return tenant
    tenant_id = getattr(tenant, "tenant_id", None)
    return str(tenant_id) if tenant_id is not None else None


def _request_id(request: Any) -> str | None:
    value = getattr(getattr(request, "state", None), "request_id", None)
    return str(value) if value is not None else None


@Injectable()
class AuditedInterceptor(NestInterceptor):
    """Injectable interceptor -- register once on the app and it fires for
    every handler that carries ``@Audited(...)`` metadata."""

    def __init__(self, service: AuditLogService):
        self._service = service

    async def intercept(self, context: ExecutionContext, next: CallHandler) -> Any:
        handler = context.get_handler()
        controller = context.get_class()
        spec = get_audit_spec(handler) or get_audit_spec(controller)
        if spec is None:
            # Route not marked -- pass through untouched.
            return await next.handle()

        request = context.get_request()
        actor = _actor(request)
        tenant_id = _tenant(request)
        request_id = _request_id(request)

        try:
            result = await next.handle()
        except Exception as exc:
            resource_id = _resolve_resource_id(spec, request, None)
            metadata: dict[str, Any] = {
                "exception": type(exc).__name__,
                "message": str(exc),
            }
            await self._service.record(
                AuditLogService.build_event(
                    action=spec.action,
                    resource_type=spec.resource_type,
                    outcome="failure",
                    resource_id=resource_id,
                    actor=actor,
                    tenant_id=tenant_id,
                    metadata=metadata,
                    request_id=request_id,
                )
            )
            raise

        resource_id = _resolve_resource_id(spec, request, result)
        metadata = {}
        if spec.capture_result:
            # ``result`` is whatever the handler returned -- almost always a pydantic response DTO,
            # sometimes carrying ``datetime``s -- and the store's ``metadata_json`` column is a plain
            # JSON column (``json.dumps`` under the hood): encode through the same FastAPI machinery
            # the framework already uses for response bodies (``core/app.py``) so this never raises
            # a driver-level serialization error for the overwhelmingly common non-dict-of-primitives
            # case.
            metadata["result"] = jsonable_encoder(result)
        await self._service.record(
            AuditLogService.build_event(
                action=spec.action,
                resource_type=spec.resource_type,
                outcome="success",
                resource_id=resource_id,
                actor=actor,
                tenant_id=tenant_id,
                metadata=metadata,
                request_id=request_id,
            )
        )
        return result
