from __future__ import annotations

import base64
import hashlib
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from austial.auth import (
    GitHubOAuth,
    GoogleOAuth,
    MicrosoftOAuth,
    OAuth2Provider,
    OAuthError,
    generate_state,
    verify_state,
)


def provider(handler, **overrides) -> OAuth2Provider:
    options: dict[str, Any] = dict(
        name="acme",
        client_id="cid",
        client_secret="secret",
        redirect_uri="https://app.example.com/cb",
        authorize_url="https://idp.example.com/authorize",
        token_url="https://idp.example.com/token",
        userinfo_url="https://idp.example.com/userinfo",
        scopes=("openid", "email"),
        transport=httpx.MockTransport(handler),
    )
    options.update(overrides)
    return OAuth2Provider(**options)


def test_authorization_url_carries_state_scopes_and_pkce() -> None:
    request = provider(lambda r: httpx.Response(200)).authorization_url()
    query = parse_qs(urlparse(request.url).query)
    assert request.url.startswith("https://idp.example.com/authorize?")
    assert query["response_type"] == ["code"] and query["client_id"] == ["cid"]
    assert query["redirect_uri"] == ["https://app.example.com/cb"] and query["scope"] == ["openid email"]
    assert query["state"] == [request.state] and len(request.state) >= 32
    # the challenge is the SHA-256 of the verifier we keep
    assert request.code_verifier is not None
    expected = base64.urlsafe_b64encode(hashlib.sha256(request.code_verifier.encode()).digest()).rstrip(b"=").decode()
    assert query["code_challenge"] == [expected] and query["code_challenge_method"] == ["S256"]
    assert request.code_verifier != provider(lambda r: httpx.Response(200)).authorization_url().code_verifier


def test_authorization_url_options() -> None:
    p = provider(lambda r: httpx.Response(200), use_pkce=False, authorize_params={"prompt": "login"})
    request = p.authorization_url(state="fixed", scopes=("a", "b"))
    query = parse_qs(urlparse(request.url).query)
    assert request.code_verifier is None and "code_challenge" not in query
    assert query["state"] == ["fixed"] and query["scope"] == ["a b"] and query["prompt"] == ["login"]
    assert "scope" not in parse_qs(urlparse(p.authorization_url(scopes=()).url).query)
    existing = provider(lambda r: httpx.Response(200), authorize_url="https://idp/authorize?tenant=1")
    assert "?tenant=1&response_type=code" in existing.authorization_url().url  # existing query kept


async def test_exchange_code_posts_the_right_form_and_parses_tokens() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["form"] = dict(httpx.QueryParams(request.content.decode()))
        seen["accept"] = request.headers["accept"]
        return httpx.Response(
            200,
            json={
                "access_token": "AT", "refresh_token": "RT", "expires_in": 3600, "id_token": "IDT",
                "token_type": "bearer", "scope": "openid email",
            },
        )  # fmt: skip

    tokens = await provider(handler).exchange_code("the-code", code_verifier="the-verifier")
    assert seen["form"] == {
        "grant_type": "authorization_code",
        "code": "the-code",
        "redirect_uri": "https://app.example.com/cb",
        "client_id": "cid",
        "client_secret": "secret",
        "code_verifier": "the-verifier",
    }
    assert seen["accept"] == "application/json"
    assert (tokens.access_token, tokens.refresh_token, tokens.expires_in, tokens.id_token) == ("AT", "RT", 3600, "IDT")
    assert tokens.token_type == "bearer" and tokens.raw["scope"] == "openid email"


async def test_refresh_and_failures() -> None:
    forms: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        forms.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"access_token": "NEW"})

    assert (await provider(handler).refresh("RT")).access_token == "NEW"
    assert forms[0]["grant_type"] == "refresh_token" and forms[0]["refresh_token"] == "RT"

    bad_code = provider(
        lambda r: httpx.Response(400, json={"error": "invalid_grant", "error_description": "code expired"})
    )
    with pytest.raises(OAuthError, match="code expired") as caught:
        await bad_code.exchange_code("x")
    assert caught.value.status_code == 400 and caught.value.payload["error"] == "invalid_grant"

    # GitHub-style: HTTP 200 with an error in the body
    with pytest.raises(OAuthError, match="bad_verification_code"):
        await provider(lambda r: httpx.Response(200, json={"error": "bad_verification_code"})).exchange_code("x")
    with pytest.raises(OAuthError, match="HTTP 500"):
        await provider(lambda r: httpx.Response(500, text="oops")).exchange_code("x")
    with pytest.raises(OAuthError):
        await provider(lambda r: httpx.Response(200, json={"no": "token"})).exchange_code("x")


async def test_fetch_user() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer AT"
        return httpx.Response(200, json={"sub": "1", "email": "ada@example.com"})

    assert (await provider(handler).fetch_user("AT"))["email"] == "ada@example.com"
    with pytest.raises(OAuthError, match="HTTP 401"):
        await provider(lambda r: httpx.Response(401, json={})).fetch_user("bad")
    with pytest.raises(OAuthError, match="no userinfo_url"):
        await provider(handler, userinfo_url=None).fetch_user("AT")


def test_state_helpers() -> None:
    state = generate_state()
    assert state != generate_state() and len(state) >= 32
    verify_state(state, state)
    for bad in ("different", "", None):
        with pytest.raises(OAuthError, match="Invalid OAuth state"):
            verify_state(state, bad)  # type: ignore[arg-type]
    with pytest.raises(OAuthError):
        verify_state("", "")  # an empty/missing saved state never validates


def test_provider_presets() -> None:
    google = GoogleOAuth(client_id="g", client_secret="s", redirect_uri="https://x/cb")
    assert google.authorize_url.startswith("https://accounts.google.com/") and google.use_pkce
    assert "access_type=offline" in google.authorization_url().url
    github = GitHubOAuth(client_id="h", client_secret="s", redirect_uri="https://x/cb")
    assert github.token_url == "https://github.com/login/oauth/access_token" and not github.use_pkce
    ms = MicrosoftOAuth(client_id="m", client_secret="s", redirect_uri="https://x/cb", tenant="contoso")
    assert "/contoso/oauth2/v2.0/authorize" in ms.authorize_url and (ms.userinfo_url or "").endswith("/oidc/userinfo")


async def test_oidc_discovery() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://issuer.example.com/.well-known/openid-configuration"
        return httpx.Response(
            200,
            json={
                "authorization_endpoint": "https://issuer.example.com/auth",
                "token_endpoint": "https://issuer.example.com/token",
                "userinfo_endpoint": "https://issuer.example.com/me",
            },
        )

    p = await OAuth2Provider.from_oidc_discovery(
        "https://issuer.example.com/", name="corp", client_id="c", client_secret="s",
        redirect_uri="https://x/cb", transport=httpx.MockTransport(handler),
    )  # fmt: skip
    assert (p.authorize_url, p.token_url, p.userinfo_url) == (
        "https://issuer.example.com/auth",
        "https://issuer.example.com/token",
        "https://issuer.example.com/me",
    )
    assert p.scopes == ("openid", "email", "profile")
    with pytest.raises(OAuthError, match="discovery failed"):
        await OAuth2Provider.from_oidc_discovery(
            "https://x", name="n", client_id="c", client_secret="s", redirect_uri="u",
            transport=httpx.MockTransport(lambda r: httpx.Response(404)),
        )  # fmt: skip


# -- ID token verification -----------------------------------------------------------------

import json  # noqa: E402
import time  # noqa: E402

import jwt  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402


def make_key(kid: str):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return pem, jwk


KEY_A, JWK_A = make_key("a")
KEY_B, JWK_B = make_key("b")
OTHER_KEY, _ = make_key("a")  # same kid as A, different material: a forgery


def id_token(key=KEY_A, kid="a", **overrides) -> str:
    now = int(time.time())
    claims = {"iss": "https://idp.example.com", "aud": "cid", "sub": "42", "email": "ada@example.com",
              "iat": now, "exp": now + 300, "nonce": "n-1"}  # fmt: skip
    claims.update(overrides)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm="RS256", headers={"kid": kid})


def verifier(keys: list[dict], fetches: list[int] | None = None, **overrides) -> OAuth2Provider:
    def handler(request: httpx.Request) -> httpx.Response:
        if fetches is not None:
            fetches.append(1)
        return httpx.Response(200, json={"keys": keys})

    return provider(handler, jwks_uri="https://idp.example.com/jwks", issuer="https://idp.example.com", **overrides)


async def test_valid_id_token_returns_claims_and_checks_nonce() -> None:
    p = verifier([JWK_A])
    claims = await p.verify_id_token(id_token(), nonce="n-1")
    assert claims["sub"] == "42" and claims["email"] == "ada@example.com"
    await p.verify_id_token(id_token())  # nonce check is optional
    with pytest.raises(OAuthError, match="nonce mismatch"):
        await p.verify_id_token(id_token(), nonce="someone-elses")


@pytest.mark.parametrize(
    ("token", "message"),
    [
        (lambda: id_token(aud="another-client"), "InvalidAudienceError"),
        (lambda: id_token(iss="https://evil.example.com"), "InvalidIssuerError"),
        (lambda: id_token(exp=int(time.time()) - 3600, iat=int(time.time()) - 7200), "ExpiredSignatureError"),
        (lambda: id_token(key=OTHER_KEY), "InvalidSignatureError"),
        (lambda: id_token(exp=None), "MissingRequiredClaimError"),
        (lambda: "not.a.jwt", "malformed ID token"),
    ],
)
async def test_invalid_id_tokens_are_rejected(token, message) -> None:
    with pytest.raises(OAuthError, match=message):
        await verifier([JWK_A]).verify_id_token(token())


async def test_unsupported_algorithms_are_rejected_before_any_key_is_used() -> None:
    fetches: list[int] = []
    p = verifier([JWK_A], fetches)
    hmac_token = jwt.encode(
        {"aud": "cid", "exp": int(time.time()) + 60, "iat": int(time.time())}, "secret", algorithm="HS256"
    )
    with pytest.raises(OAuthError, match="unsupported algorithm 'HS256'"):
        await p.verify_id_token(hmac_token)  # the classic RS256->HS256 confusion attack
    none_token = jwt.encode({"aud": "cid"}, None, algorithm="none")  # type: ignore[arg-type]
    with pytest.raises(OAuthError, match="unsupported algorithm 'none'"):
        await p.verify_id_token(none_token)
    assert fetches == []


async def test_jwks_are_cached_and_refetched_once_on_rotation() -> None:
    fetches: list[int] = []
    p = verifier([JWK_A], fetches)
    await p.verify_id_token(id_token())
    await p.verify_id_token(id_token())
    assert len(fetches) == 1  # cached

    with pytest.raises(OAuthError, match="no signing key"):
        await p.verify_id_token(id_token(key=KEY_B, kid="b"))  # unknown kid -> one refetch, still unknown
    assert len(fetches) == 2

    keys = [JWK_A]
    rotating = provider(
        lambda r: httpx.Response(200, json={"keys": keys}),
        jwks_uri="https://idp.example.com/jwks",
        issuer="https://idp.example.com",
    )
    await rotating.verify_id_token(id_token())
    keys.append(JWK_B)  # the provider rotates in key b
    assert (await rotating.verify_id_token(id_token(key=KEY_B, kid="b")))["sub"] == "42"


async def test_jwks_failures_and_missing_configuration() -> None:
    with pytest.raises(OAuthError, match="no jwks_uri"):
        await provider(lambda r: httpx.Response(200)).verify_id_token(id_token())
    down = provider(lambda r: httpx.Response(503), jwks_uri="https://idp.example.com/jwks")
    with pytest.raises(OAuthError, match="HTTP 503"):
        await down.verify_id_token(id_token())


def test_openid_scope_adds_a_nonce_and_presets_know_their_keys() -> None:
    request = provider(lambda r: httpx.Response(200)).authorization_url()
    assert request.nonce and parse_qs(urlparse(request.url).query)["nonce"] == [request.nonce]
    plain = provider(lambda r: httpx.Response(200), scopes=("email",)).authorization_url()
    assert plain.nonce is None and "nonce" not in parse_qs(urlparse(plain.url).query)

    google = GoogleOAuth(client_id="g", client_secret="s", redirect_uri="u")
    assert google.jwks_uri == "https://www.googleapis.com/oauth2/v3/certs"
    assert google.issuer == ("https://accounts.google.com", "accounts.google.com")
    pinned = MicrosoftOAuth(client_id="m", client_secret="s", redirect_uri="u", tenant="contoso")
    assert pinned.issuer == "https://login.microsoftonline.com/contoso/v2.0" and "contoso" in (pinned.jwks_uri or "")
    assert MicrosoftOAuth(client_id="m", client_secret="s", redirect_uri="u").issuer is None  # multi-tenant: unpinned


async def test_discovery_carries_jwks_and_issuer_so_verification_just_works() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": "https://idp.example.com",
                    "authorization_endpoint": "https://idp.example.com/auth",
                    "token_endpoint": "https://idp.example.com/token",
                    "jwks_uri": "https://idp.example.com/jwks",
                },
            )
        return httpx.Response(200, json={"keys": [JWK_A]})

    p = await OAuth2Provider.from_oidc_discovery(
        "https://idp.example.com", name="corp", client_id="cid", client_secret="s", redirect_uri="u",
        transport=httpx.MockTransport(handler),
    )  # fmt: skip
    assert (await p.verify_id_token(id_token()))["sub"] == "42"
