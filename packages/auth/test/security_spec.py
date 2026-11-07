"""``austial.security`` unit tests.

Covers each primitive shipped by the package:

- ``PIIRedactor`` masks email, phone, PAN, Aadhaar, passport, IBAN and Luhn-valid
  card numbers, and passes non-matching text through.
- ``EnvelopeEncryptor`` round-trips a plaintext, rejects tampered ciphertext,
  supports multi-version key rotation, and refuses invalid key material.
- ``RateLimitGuard`` allows a caller up to the configured budget, rejects the
  next request, and resets on a fresh window.
- ``IdempotencyKeyGuard`` allows a first request, replays a cached response for
  the same key + body, rejects on the same key + different body, and honours
  TTL expiry.
- ``CsrfInterceptor`` passes when header + cookie match, fails on mismatch,
  and short-circuits when a bearer token is present.
- ``SecureHeadersMiddleware`` sets each header on the response.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.responses import Response

from austial.common import ExecutionContext
from austial.common.exceptions import ForbiddenException
from austial.common.interceptors.base import CallHandler
from austial.security import (
    CsrfInterceptor,
    EncryptionKeyError,
    EnvelopeEncryptor,
    IdempotencyConflictError,
    IdempotencyKeyGuard,
    IdempotencyRecord,
    InMemoryIdempotencyStore,
    InMemoryRateLimitStore,
    PIIRedactor,
    RateLimit,
    RateLimitExceededError,
    RateLimitGuard,
    SecureHeadersMiddleware,
    SecurityConfig,
)

# ---------------------------------------------------------------------------
# Test doubles


class _FakeCtx(ExecutionContext):
    def __init__(self, request: Any, controller_class: type = object, handler: Any = None) -> None:
        self._req = request
        self._cls = controller_class
        self._h = handler or (lambda: None)

    def get_request(self) -> Any:
        return self._req

    def get_class(self) -> type:
        return self._cls

    def get_handler(self) -> Any:
        return self._h


def _request(
    *,
    method: str = "GET",
    path: str = "/",
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    client_ip: str = "203.0.113.7",
    body: bytes | None = None,
) -> Any:
    state = SimpleNamespace()
    return SimpleNamespace(
        method=method,
        url=SimpleNamespace(path=path),
        headers=(headers or {}),
        cookies=(cookies or {}),
        client=SimpleNamespace(host=client_ip),
        state=state,
        body_bytes=body or b"",
    )


class _Call(CallHandler):
    """Minimal ``CallHandler`` stand-in for interceptor tests."""

    def __init__(self, value: Any = "ok") -> None:
        self.value = value
        self.called = False

    async def handle(self) -> Any:
        self.called = True
        return self.value


# ---------------------------------------------------------------------------
# PIIRedactor


def test_pii_redactor_masks_email():
    out = PIIRedactor().redact("contact alice@example.com please")
    assert "alice" not in out and "@example.com" in out


def test_pii_redactor_masks_phone():
    assert "[REDACTED-PHONE]" in PIIRedactor().redact("Call +91 98765 43210 today")


def test_pii_redactor_masks_pan_aadhaar_and_passport():
    text = "PAN AAAPL1234C Aadhaar 1234 5678 9012 passport K1234567"
    out = PIIRedactor().redact(text)
    assert "AAAPL1234C" not in out
    assert "1234 5678 9012" not in out
    assert "K1234567" not in out


def test_pii_redactor_masks_luhn_valid_card():
    # 4111 1111 1111 1111 is the classic Visa test number (Luhn-valid)
    out = PIIRedactor().redact("card 4111 1111 1111 1111 was used")
    assert "[REDACTED-CARD-1111]" in out


def test_pii_redactor_leaves_non_pii_alone():
    text = "The build finished in 12 seconds"
    assert PIIRedactor().redact(text) == text


def test_pii_redactor_masks_iban():
    # Published test IBAN with a valid mod-97 check
    out = PIIRedactor().redact("wire from GB82WEST12345698765432 to us")
    assert "GB82WEST12345698765432" not in out


def test_pii_redactor_recurses_into_dicts_and_lists():
    payload = {"email": "bob@example.com", "tags": ["safe", "call +91 9876543210"]}
    out = PIIRedactor().redact(payload)
    assert "bob" not in out["email"]
    assert "[REDACTED-PHONE]" in out["tags"][1]


# ---------------------------------------------------------------------------
# EnvelopeEncryptor


def _key(byte: int) -> bytes:
    return bytes([byte]) * 32


def test_envelope_encryptor_round_trip():
    enc = EnvelopeEncryptor(keys={"k1": _key(0x11)}, active_key="k1")
    ciphertext = enc.encrypt("account:12345")
    assert ciphertext != "account:12345"
    assert enc.decrypt(ciphertext) == "account:12345"


def test_envelope_encryptor_rejects_wrong_key():
    enc = EnvelopeEncryptor(keys={"k1": _key(0x11)}, active_key="k1")
    ciphertext = enc.encrypt("secret")

    # A different encryptor whose "k1" is a different byte string cannot decrypt.
    other = EnvelopeEncryptor(keys={"k1": _key(0x22)}, active_key="k1")
    with pytest.raises(EncryptionKeyError):
        other.decrypt(ciphertext)


def test_envelope_encryptor_reads_rotated_key_version():
    old = EnvelopeEncryptor(keys={"v1": _key(0x11)}, active_key="v1")
    ciphertext_v1 = old.encrypt("legacy")

    rotated = EnvelopeEncryptor(
        keys={"v1": _key(0x11), "v2": _key(0x33)},
        active_key="v2",
    )
    # New writes go under v2, but the v1 ciphertext still decrypts.
    assert rotated.decrypt(ciphertext_v1) == "legacy"
    new = rotated.encrypt("fresh")
    assert new != ciphertext_v1
    assert rotated.decrypt(new) == "fresh"


def test_envelope_encryptor_rejects_wrong_length_key():
    with pytest.raises(EncryptionKeyError):
        EnvelopeEncryptor(keys={"k1": b"short"}, active_key="k1")


def test_envelope_encryptor_rejects_missing_active_key():
    with pytest.raises(EncryptionKeyError):
        EnvelopeEncryptor(keys={"k1": _key(0x11)}, active_key="missing")


# ---------------------------------------------------------------------------
# RateLimitGuard


@pytest.mark.asyncio
async def test_rate_limit_guard_allows_up_to_limit_then_blocks(monkeypatch):
    store = InMemoryRateLimitStore()
    config = SecurityConfig(default_rate_limit=(3, 60))
    guard = RateLimitGuard(store, config)

    fake_now = [1_700_000_000]
    monkeypatch.setattr(time, "time", lambda: fake_now[0])

    req = _request(method="GET", path="/x", client_ip="203.0.113.9")
    ctx = _FakeCtx(req)

    for _ in range(3):
        assert await guard.can_activate(ctx) is True

    with pytest.raises(RateLimitExceededError):
        await guard.can_activate(ctx)


@pytest.mark.asyncio
async def test_rate_limit_guard_resets_after_window(monkeypatch):
    store = InMemoryRateLimitStore()
    config = SecurityConfig(default_rate_limit=(1, 60))
    guard = RateLimitGuard(store, config)

    fake_now = [1_700_000_000]
    monkeypatch.setattr(time, "time", lambda: fake_now[0])

    req = _request(client_ip="203.0.113.9", path="/y")
    ctx = _FakeCtx(req)

    assert await guard.can_activate(ctx) is True
    with pytest.raises(RateLimitExceededError):
        await guard.can_activate(ctx)

    # Advance past the window boundary; the counter must reset.
    fake_now[0] += 61
    assert await guard.can_activate(ctx) is True


@pytest.mark.asyncio
async def test_rate_limit_guard_reads_decorator_override():
    store = InMemoryRateLimitStore()
    config = SecurityConfig(default_rate_limit=(1000, 60))
    guard = RateLimitGuard(store, config)

    @RateLimit(2, 60)
    def handler() -> None:
        pass

    ctx = _FakeCtx(_request(client_ip="10.0.0.1", path="/tight"), handler=handler)

    assert await guard.can_activate(ctx) is True
    assert await guard.can_activate(ctx) is True
    with pytest.raises(RateLimitExceededError):
        await guard.can_activate(ctx)


def test_rate_limit_decorator_rejects_invalid_values():
    with pytest.raises(ValueError):
        RateLimit(0, 60)
    with pytest.raises(ValueError):
        RateLimit(10, 0)


# ---------------------------------------------------------------------------
# IdempotencyKeyGuard


@pytest.mark.asyncio
async def test_idempotency_first_request_passes_through_and_seeds_state():
    store = InMemoryIdempotencyStore(ttl_seconds=60)
    guard = IdempotencyKeyGuard(store)
    req = _request(method="POST", path="/pay", headers={"Idempotency-Key": "abc"}, body=b'{"amount": 100}')

    assert await guard.can_activate(_FakeCtx(req)) is True
    assert getattr(req.state, "idempotent_replay", None) is None
    assert req.state.idempotency_key == "abc"


@pytest.mark.asyncio
async def test_idempotency_replay_flags_cached_record():
    store = InMemoryIdempotencyStore(ttl_seconds=60)
    guard = IdempotencyKeyGuard(store)
    req = _request(method="POST", path="/pay", headers={"Idempotency-Key": "abc"}, body=b'{"amount": 100}')

    # Simulate the first request completing: hash the body, store an outcome.
    ctx = _FakeCtx(req)
    await guard.can_activate(ctx)
    store.put(
        IdempotencyRecord(
            key="abc",
            request_hash=req.state.idempotency_request_hash,
            status_code=201,
            body={"id": "txn_1"},
            stored_at=time.time(),
        )
    )

    # A second request with the same body must be flagged as a replay.
    req2 = _request(method="POST", path="/pay", headers={"Idempotency-Key": "abc"}, body=b'{"amount": 100}')
    assert await guard.can_activate(_FakeCtx(req2)) is True
    assert req2.state.idempotent_replay.body == {"id": "txn_1"}


@pytest.mark.asyncio
async def test_idempotency_conflict_on_different_body():
    store = InMemoryIdempotencyStore(ttl_seconds=60)
    guard = IdempotencyKeyGuard(store)
    req = _request(method="POST", path="/pay", headers={"Idempotency-Key": "abc"}, body=b'{"amount": 100}')
    await guard.can_activate(_FakeCtx(req))
    store.put(
        IdempotencyRecord(
            key="abc",
            request_hash=req.state.idempotency_request_hash,
            status_code=201,
            body={"id": "txn_1"},
            stored_at=time.time(),
        )
    )

    # Same key, different body => conflict
    req2 = _request(method="POST", path="/pay", headers={"Idempotency-Key": "abc"}, body=b'{"amount": 999}')
    with pytest.raises(IdempotencyConflictError):
        await guard.can_activate(_FakeCtx(req2))


@pytest.mark.asyncio
async def test_idempotency_ttl_expires_record():
    store = InMemoryIdempotencyStore(ttl_seconds=1)
    guard = IdempotencyKeyGuard(store)
    req = _request(method="POST", path="/pay", headers={"Idempotency-Key": "abc"}, body=b"{}")
    await guard.can_activate(_FakeCtx(req))
    store.put(
        IdempotencyRecord(
            key="abc",
            request_hash=req.state.idempotency_request_hash,
            status_code=201,
            body={},
            stored_at=time.time() - 10,  # already expired
        )
    )

    # Expired record => guard behaves like a first request (no replay flag).
    req2 = _request(method="POST", path="/pay", headers={"Idempotency-Key": "abc"}, body=b"{}")
    assert await guard.can_activate(_FakeCtx(req2)) is True
    assert getattr(req2.state, "idempotent_replay", None) is None


@pytest.mark.asyncio
async def test_idempotency_read_method_is_noop():
    store = InMemoryIdempotencyStore()
    guard = IdempotencyKeyGuard(store)
    req = _request(method="GET", path="/pay", headers={"Idempotency-Key": "abc"})
    assert await guard.can_activate(_FakeCtx(req)) is True


# ---------------------------------------------------------------------------
# CsrfInterceptor


@pytest.mark.asyncio
async def test_csrf_passes_on_matching_header_and_cookie():
    interceptor = CsrfInterceptor()
    req = _request(
        method="POST",
        path="/write",
        headers={"X-CSRF-Token": "tok-123"},
        cookies={"csrf_token": "tok-123"},
    )
    call = _Call(value="handled")
    assert await interceptor.intercept(_FakeCtx(req), call) == "handled"
    assert call.called


@pytest.mark.asyncio
async def test_csrf_rejects_on_mismatch():
    interceptor = CsrfInterceptor()
    req = _request(
        method="POST",
        path="/write",
        headers={"X-CSRF-Token": "tok-abc"},
        cookies={"csrf_token": "tok-xyz"},
    )
    with pytest.raises(ForbiddenException):
        await interceptor.intercept(_FakeCtx(req), _Call())


@pytest.mark.asyncio
async def test_csrf_skips_on_bearer_auth():
    interceptor = CsrfInterceptor()
    req = _request(
        method="POST",
        path="/write",
        headers={"Authorization": "Bearer some-jwt"},
        cookies={},
    )
    call = _Call("ok")
    # No CSRF header/cookie needed for a bearer-authenticated request.
    assert await interceptor.intercept(_FakeCtx(req), call) == "ok"


@pytest.mark.asyncio
async def test_csrf_allows_safe_methods():
    interceptor = CsrfInterceptor()
    req = _request(method="GET", path="/read", headers={}, cookies={})
    assert await interceptor.intercept(_FakeCtx(req), _Call("read")) == "read"


# ---------------------------------------------------------------------------
# SecureHeadersMiddleware


@pytest.mark.asyncio
async def test_secure_headers_sets_every_header():
    config = SecurityConfig()
    middleware = SecureHeadersMiddleware(config)
    response = Response()

    async def call_next() -> Response:
        return response

    result = await middleware.use(_request(), call_next)
    assert result is response
    assert result.headers["Content-Security-Policy"] == config.csp
    assert result.headers["Strict-Transport-Security"].startswith(f"max-age={config.hsts_max_age}")
    assert result.headers["X-Content-Type-Options"] == "nosniff"
    assert result.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert result.headers["X-Frame-Options"] == "DENY"
    assert result.headers["Permissions-Policy"] == config.permissions_policy


@pytest.mark.asyncio
async def test_secure_headers_respects_custom_csp():
    config = SecurityConfig(csp="default-src 'none'")
    middleware = SecureHeadersMiddleware(config)
    response = Response()

    async def call_next() -> Response:
        return response

    await middleware.use(_request(), call_next)
    assert response.headers["Content-Security-Policy"] == "default-src 'none'"


# ---------------------------------------------------------------------------
# RateLimitGuard client-IP resolution (X-Forwarded-For is client-controlled)


def _limited_ip(config: SecurityConfig, *, xff: str | None) -> str:
    guard = RateLimitGuard(InMemoryRateLimitStore(), config)
    headers = {"X-Forwarded-For": xff} if xff else {}
    return guard._client_ip(_request(headers=headers, client_ip="198.51.100.1"))


def test_rate_limit_ignores_forwarded_for_by_default():
    # A spoofed header must not mint a fresh bucket per request.
    assert _limited_ip(SecurityConfig(), xff="1.2.3.4") == "198.51.100.1"


def test_rate_limit_takes_the_trusted_hop_from_the_right():
    config = SecurityConfig(trusted_proxy_hops=1)
    # client-supplied "6.6.6.6" then the address our single trusted proxy saw
    assert _limited_ip(config, xff="6.6.6.6, 203.0.113.50") == "203.0.113.50"


def test_rate_limit_ignores_a_chain_shorter_than_the_trusted_hops():
    assert _limited_ip(SecurityConfig(trusted_proxy_hops=2), xff="203.0.113.50") == "198.51.100.1"
