"""``IdempotencyKeyGuard`` -- enforces ``Idempotency-Key`` on write methods.

For ``POST``/``PUT``/``PATCH``/``DELETE`` the guard reads the header
``Idempotency-Key``:

- Missing header: guard is a no-op (allow through). Product code can require it
  by decorating the route with a companion validator.
- Header present, no cached record: allow through; the framework's response
  interceptor stores the outcome (product code calls
  ``store.put(IdempotencyRecord(...))`` from a middleware/interceptor once the
  handler returns).
- Header present, cached record with the same body hash: replay the cached
  response by short-circuiting the pipeline. This is done by attaching the
  record to ``request.state.idempotent_replay``; the response interceptor is
  expected to render it.
- Header present, cached record with a *different* body hash: 409 conflict.

Read-only methods (``GET``/``HEAD``/``OPTIONS``) are allowed unconditionally --
they are already idempotent by definition and rarely mutate state.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from austial.common.decorators.injectable import Injectable
from austial.common.guards.base import CanActivate, ExecutionContext
from austial.security.errors import IdempotencyConflictError
from austial.security.idempotency_store import IdempotencyStore

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@Injectable()
class IdempotencyKeyGuard(CanActivate):
    def __init__(self, store: IdempotencyStore) -> None:
        self._store = store

    async def can_activate(self, context: ExecutionContext) -> bool:
        request = context.get_request()
        method = getattr(request, "method", "GET").upper()
        if method not in _WRITE_METHODS:
            return True

        headers = getattr(request, "headers", {}) or {}
        key = _header(headers, "Idempotency-Key")
        if not key:
            return True

        request_hash = await self._hash_request(request, method)
        cached = self._store.get(key)
        if cached is None:
            # cache miss: allow through; product code stores after handler runs
            request.state.idempotency_key = key
            request.state.idempotency_request_hash = request_hash
            return True

        if cached.request_hash != request_hash:
            raise IdempotencyConflictError(
                f"Idempotency-Key '{key}' has already been used with a different request payload"
            )

        # cache hit: signal replay
        request.state.idempotent_replay = cached
        return True

    async def _hash_request(self, request: Any, method: str) -> str:
        path = getattr(getattr(request, "url", None), "path", "") or getattr(request, "path", "/")
        body_bytes = await _body(request)
        digest = hashlib.sha256()
        digest.update(method.encode("ascii"))
        digest.update(b"\0")
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(body_bytes)
        return digest.hexdigest()


def _header(headers: Any, name: str) -> str | None:
    try:
        value = headers.get(name)
    except AttributeError:
        return None
    if value:
        return value
    try:
        return headers.get(name.lower())
    except AttributeError:
        return None


async def _body(request: Any) -> bytes:
    """Read the request body. Starlette exposes ``await request.body()``; a test
    double may attach ``body_bytes`` directly or provide a dict."""
    # cached body written by prior guards/middleware
    cached = getattr(getattr(request, "state", None), "raw_body", None)
    if isinstance(cached, (bytes, bytearray)):
        return bytes(cached)

    body_attr = getattr(request, "body", None)
    if callable(body_attr):
        result = body_attr()
        if hasattr(result, "__await__"):
            result = await result
        if isinstance(result, (bytes, bytearray)):
            return bytes(result)
        if isinstance(result, str):
            return result.encode("utf-8")
    if isinstance(body_attr, (bytes, bytearray)):
        return bytes(body_attr)
    if isinstance(body_attr, str):
        return body_attr.encode("utf-8")

    body_bytes = getattr(request, "body_bytes", None)
    if isinstance(body_bytes, (bytes, bytearray)):
        return bytes(body_bytes)

    payload = getattr(request, "json_body", None)
    if payload is not None:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    return b""
