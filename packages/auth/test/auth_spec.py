"""``austial.auth`` unit tests.

Covers the five load-bearing behaviours a product depends on:

- Argon2 hash-and-verify round-trip; a wrong password fails; a hash produced with
  weaker parameters is flagged for rehash.
- JWT sign-and-verify round-trip; an expired token surfaces ``TokenExpiredError``;
  a tampered token surfaces ``InvalidTokenError``.
- TOTP secret-and-verify round-trip; the wrong code fails; recovery codes are unique
  and correctly grouped.
- ``InMemoryRefreshTokenStore`` issue → rotate → revoke lifecycle.
- ``AuthGuard`` allows ``@Public`` routes, rejects requests without a bearer token,
  and populates ``request.state.user`` on a valid token.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from austial.auth import (
    Argon2Hasher,
    AuthConfig,
    AuthGuard,
    AuthPrincipal,
    AuthService,
    InMemoryRefreshTokenStore,
    InvalidTokenError,
    JwtStrategy,
    PasswordVerificationError,
    Public,
    TokenExpiredError,
    TotpStrategy,
)
from austial.common import ExecutionContext
from austial.common.exceptions import UnauthorizedException


class _FakeExecutionContext(ExecutionContext):
    def __init__(self, request, controller_class, handler):
        self._request = request
        self._controller_class = controller_class
        self._handler = handler

    def get_request(self):
        return self._request

    def get_class(self):
        return self._controller_class

    def get_handler(self):
        return self._handler


def _fake_request(headers: dict[str, str] | None = None):
    class _State:
        pass

    return SimpleNamespace(headers=headers or {}, state=_State())


# ---------------------------------------------------------------------------
# Argon2Hasher


def test_argon2_hash_and_verify_round_trip():
    hasher = Argon2Hasher()
    encoded = hasher.hash("hunter2!")
    hasher.verify("hunter2!", encoded)  # must not raise


def test_argon2_verify_rejects_wrong_password():
    hasher = Argon2Hasher()
    encoded = hasher.hash("hunter2!")
    with pytest.raises(PasswordVerificationError):
        hasher.verify("nope", encoded)


def test_argon2_needs_rehash_flags_weaker_parameters():
    weak = Argon2Hasher(time_cost=1, memory_cost=8 * 1024, parallelism=1)
    strong = Argon2Hasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)
    old = weak.hash("hunter2!")
    assert strong.needs_rehash(old) is True


# ---------------------------------------------------------------------------
# JwtStrategy


def _jwt() -> JwtStrategy:
    return JwtStrategy(secret="x" * 40, issuer="austial-tests", access_ttl=timedelta(minutes=15))


def test_jwt_sign_and_verify_round_trip():
    jwt = _jwt()
    token = jwt.sign("user-1", claims={"tenant": "acme", "roles": ["ops"]})
    decoded = jwt.verify(token)
    assert decoded.subject == "user-1"
    assert decoded.claims == {"tenant": "acme", "roles": ["ops"]}
    assert decoded.issuer == "austial-tests"
    assert decoded.token_id is not None


def test_jwt_rejects_expired_token():
    # ttl beyond the default 30s clock-skew leeway
    jwt = JwtStrategy(secret="x" * 40, issuer="austial-tests", access_ttl=timedelta(seconds=-120))
    token = jwt.sign("user-1")
    with pytest.raises(TokenExpiredError):
        jwt.verify(token)


def test_jwt_rejects_tampered_signature():
    jwt = _jwt()
    token = jwt.sign("user-1")
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    with pytest.raises(InvalidTokenError):
        jwt.verify(tampered)


def test_jwt_secret_must_be_long_enough():
    with pytest.raises(ValueError):
        JwtStrategy(secret="short", issuer="x")


# ---------------------------------------------------------------------------
# TotpStrategy


def test_totp_secret_and_verify_round_trip():
    totp = TotpStrategy(issuer="austial-tests")
    secret = totp.generate_secret()
    import pyotp

    code = pyotp.TOTP(secret).now()
    assert totp.verify(secret, code) is True


def test_totp_rejects_wrong_code():
    totp = TotpStrategy(issuer="austial-tests")
    secret = totp.generate_secret()
    assert totp.verify(secret, "000000") is False
    assert totp.verify(secret, "abc") is False
    assert totp.verify(secret, "") is False


def test_totp_recovery_codes_are_unique_and_formatted():
    totp = TotpStrategy(issuer="austial-tests")
    codes = totp.generate_recovery_codes(count=8, group_size=5)
    assert len(codes) == 8
    assert len(set(codes)) == 8
    for c in codes:
        left, _, right = c.partition("-")
        assert len(left) == 5 and len(right) == 5


def test_totp_provisioning_uri_is_otpauth():
    totp = TotpStrategy(issuer="austial-tests")
    uri = totp.provisioning_uri("SECRETSECRETSECRET", "user@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "issuer=austial-tests" in uri


# ---------------------------------------------------------------------------
# InMemoryRefreshTokenStore


@pytest.mark.asyncio
async def test_refresh_store_issue_rotate_revoke_lifecycle():
    store = InMemoryRefreshTokenStore()
    opaque, record = await store.issue("user-1", ttl=timedelta(minutes=5))
    assert record.subject == "user-1"

    new_opaque, new_record = await store.rotate(opaque, ttl=timedelta(minutes=5))
    assert new_opaque != opaque
    assert new_record.subject == "user-1"

    # rotating the old token again is now rejected
    with pytest.raises(LookupError):
        await store.rotate(opaque, ttl=timedelta(minutes=5))

    await store.revoke(new_opaque)
    # revoking is idempotent
    await store.revoke(new_opaque)


@pytest.mark.asyncio
async def test_refresh_store_revoke_all_for_subject():
    store = InMemoryRefreshTokenStore()
    await store.issue("u1", ttl=timedelta(minutes=5))
    await store.issue("u1", ttl=timedelta(minutes=5))
    await store.issue("u2", ttl=timedelta(minutes=5))
    revoked = await store.revoke_all_for_subject("u1")
    assert revoked == 2
    # calling again reports 0
    assert await store.revoke_all_for_subject("u1") == 0


# ---------------------------------------------------------------------------
# AuthGuard


@pytest.mark.asyncio
async def test_auth_guard_allows_public_routes():
    guard = AuthGuard(_jwt())

    @Public()
    def _handler():
        pass

    ctx = _FakeExecutionContext(_fake_request(), object, _handler)
    assert await guard.can_activate(ctx) is True


@pytest.mark.asyncio
async def test_auth_guard_rejects_missing_bearer():
    guard = AuthGuard(_jwt())

    def _handler():
        pass

    ctx = _FakeExecutionContext(_fake_request(headers={}), object, _handler)
    with pytest.raises(UnauthorizedException):
        await guard.can_activate(ctx)


@pytest.mark.asyncio
async def test_auth_guard_populates_request_state_on_valid_token():
    jwt = _jwt()
    token = jwt.sign("user-42", claims={"tenant": "acme"})
    guard = AuthGuard(jwt)

    def _handler():
        pass

    req = _fake_request(headers={"Authorization": f"Bearer {token}"})
    ctx = _FakeExecutionContext(req, object, _handler)
    assert await guard.can_activate(ctx) is True
    assert isinstance(req.state.user, AuthPrincipal)
    assert req.state.user.subject == "user-42"
    assert req.state.user.claims == {"tenant": "acme"}


# ---------------------------------------------------------------------------
# AuthService orchestration


@pytest.mark.asyncio
async def test_auth_service_issue_and_refresh_round_trip():
    jwt = _jwt()
    totp = TotpStrategy(issuer="austial-tests")
    hasher = Argon2Hasher()
    store = InMemoryRefreshTokenStore()
    config = AuthConfig(jwt_secret="x" * 40, issuer="austial-tests")
    svc = AuthService(jwt, totp, hasher, store, config)

    tokens = await svc.issue_tokens("user-1", claims={"tenant": "acme"})
    decoded = jwt.verify(tokens.access_token)
    assert decoded.subject == "user-1"

    refreshed = await svc.refresh(tokens.refresh_token)
    assert refreshed.refresh_token != tokens.refresh_token
    assert jwt.verify(refreshed.access_token).subject == "user-1"

    await svc.logout(refreshed.refresh_token)
    # a revoked refresh token cannot be used again
    from austial.auth.errors import AuthenticationError

    with pytest.raises(AuthenticationError):
        await svc.refresh(refreshed.refresh_token)
