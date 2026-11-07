"""OAuth 2.0 / OpenID Connect "sign in with ..." (authorization-code flow, PKCE), the social-login half of
what ``@nestjs/passport`` strategies give Nest.

You own the HTTP routes and the session; this gives you the protocol steps::

    google = GoogleOAuth(client_id=..., client_secret=..., redirect_uri="https://app.example.com/auth/google/callback")

    @Get("auth/google")
    async def start(self, response: Res):
        request = google.authorization_url()                      # fresh state + PKCE verifier
        response.set_cookie("oauth", sign({"s": request.state, "v": request.code_verifier}), httponly=True)
        return RedirectResponse(request.url)

    @Get("auth/google/callback")
    async def callback(self, code: str, state: str, oauth: str = Cookies("oauth")):
        saved = unsign(oauth)
        verify_state(saved["s"], state)                            # CSRF check, constant-time
        tokens = await google.exchange_code(code, code_verifier=saved["v"])
        profile = await google.fetch_user(tokens.access_token)     # {"email": ..., "name": ...}
        ...                                                        # find-or-create the user, issue your own JWT

Storing ``state`` and the verifier is your job (a signed, httponly cookie works); the redirect carries only ``state``.
ID tokens are verified by ``verify_id_token`` (signature against the provider's JWKS, audience, issuer, expiry
and nonce); or read identity from the userinfo endpoint instead.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt


class OAuthError(Exception):
    """The provider rejected a request, or state verification failed."""

    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass(frozen=True)
class AuthorizationRequest:
    url: str  # send the user's browser here
    state: str  # keep it (cookie/session) and compare it on the callback
    code_verifier: str | None  # PKCE secret: keep it too, pass it to exchange_code
    nonce: str | None = None  # OIDC replay protection: keep it and pass it to verify_id_token(nonce=...)


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    token_type: str = "Bearer"
    refresh_token: str | None = None
    expires_in: int | None = None
    id_token: str | None = None
    scope: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def verify_state(expected: str, received: str) -> None:
    """Raises :class:`OAuthError` unless ``received`` equals ``expected`` (constant-time)."""
    if not expected or not hmac.compare_digest(expected.encode(), (received or "").encode()):
        raise OAuthError("Invalid OAuth state: possible CSRF, or the login session expired")


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class OAuth2Provider:
    def __init__(
        self,
        *,
        name: str,
        client_id: str,
        client_secret: str,
        authorize_url: str,
        token_url: str,
        redirect_uri: str,
        userinfo_url: str | None = None,
        scopes: tuple[str, ...] = (),
        use_pkce: bool = True,
        authorize_params: dict[str, str] | None = None,
        jwks_uri: str | None = None,
        issuer: str | tuple[str, ...] | None = None,
        id_token_algorithms: tuple[str, ...] = ("RS256",),
        jwks_ttl: float = 3600.0,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.name, self.client_id, self.client_secret = name, client_id, client_secret
        self.authorize_url, self.token_url, self.userinfo_url = authorize_url, token_url, userinfo_url
        self.redirect_uri, self.scopes, self.use_pkce = redirect_uri, scopes, use_pkce
        self.authorize_params = authorize_params or {}
        self.jwks_uri, self.issuer = jwks_uri, issuer
        self.id_token_algorithms, self._jwks_ttl = id_token_algorithms, jwks_ttl
        self._jwks: dict[str, Any] | None = None
        self._jwks_fetched_at = 0.0
        self._timeout, self._transport = timeout, transport

    # -- step 1: send the user to the provider ------------------------------------------
    def authorization_url(
        self, *, state: str | None = None, scopes: tuple[str, ...] | None = None
    ) -> AuthorizationRequest:
        state = state or generate_state()
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes if scopes is not None else self.scopes),
            "state": state,
            **self.authorize_params,
        }
        verifier = None
        if self.use_pkce:
            verifier, challenge = _pkce_pair()
            params.update({"code_challenge": challenge, "code_challenge_method": "S256"})
        if not params["scope"]:
            del params["scope"]
        nonce = None
        if "openid" in params.get("scope", "").split():
            nonce = secrets.token_urlsafe(32)  # binds the ID token to this login attempt
            params["nonce"] = nonce
        separator = "&" if "?" in self.authorize_url else "?"
        return AuthorizationRequest(f"{self.authorize_url}{separator}{urlencode(params)}", state, verifier, nonce)

    # -- step 2: trade the code for tokens ------------------------------------------------
    async def exchange_code(self, code: str, *, code_verifier: str | None = None) -> OAuthTokens:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        return await self._token_request(data)

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        return await self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        )

    async def _token_request(self, data: dict[str, str]) -> OAuthTokens:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(self.token_url, data=data, headers={"Accept": "application/json"})
        payload = self._json(response)
        if response.is_error or "error" in payload or "access_token" not in payload:
            description = payload.get("error_description") or payload.get("error") or f"HTTP {response.status_code}"
            raise OAuthError(
                f"{self.name}: token request failed ({description})", status_code=response.status_code, payload=payload
            )
        return OAuthTokens(
            access_token=payload["access_token"],
            token_type=payload.get("token_type", "Bearer"),
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            id_token=payload.get("id_token"),
            scope=payload.get("scope"),
            raw=payload,
        )

    # -- ID tokens ------------------------------------------------------------------------
    async def _signing_keys(self, *, force: bool = False) -> dict[str, Any]:
        if self.jwks_uri is None:
            raise OAuthError(f"{self.name} has no jwks_uri configured: can't verify ID tokens")
        fresh = self._jwks is not None and time.monotonic() - self._jwks_fetched_at < self._jwks_ttl
        if force or not fresh:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.get(self.jwks_uri)
            if response.is_error:
                raise OAuthError(f"{self.name}: fetching signing keys failed (HTTP {response.status_code})")
            self._jwks = response.json()
            self._jwks_fetched_at = time.monotonic()
        assert self._jwks is not None
        return self._jwks

    async def verify_id_token(self, id_token: str, *, nonce: str | None = None, leeway: float = 60.0) -> dict[str, Any]:
        """Verifies an OIDC ID token and returns its claims.

        Checks the signature against the provider's JWKS (cached; re-fetched once if the token's ``kid`` is unknown,
        which covers key rotation), that the algorithm is one of ``id_token_algorithms`` (so ``alg: none`` and HMAC
        confusion are rejected), ``aud`` equals this client id, ``iss`` matches ``issuer`` (when configured),
        ``exp``/``iat`` with ``leeway`` seconds of clock skew, and, if given, that ``nonce`` equals the token's.
        """
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.PyJWTError as exc:
            raise OAuthError(f"{self.name}: malformed ID token ({exc})") from exc
        if header.get("alg") not in self.id_token_algorithms:
            raise OAuthError(f"{self.name}: ID token signed with unsupported algorithm {header.get('alg')!r}")

        def find(keys: dict[str, Any]) -> dict[str, Any] | None:
            for key in keys.get("keys", []):
                if key.get("kid") == header.get("kid"):
                    return key
            return None

        jwk = find(await self._signing_keys())
        if jwk is None:  # a key we haven't seen: the provider may have rotated
            jwk = find(await self._signing_keys(force=True))
        if jwk is None:
            raise OAuthError(f"{self.name}: no signing key matches the ID token's kid")
        try:
            claims = jwt.decode(
                id_token,
                jwt.PyJWK(jwk).key,
                algorithms=list(self.id_token_algorithms),
                audience=self.client_id,
                issuer=list(self.issuer) if isinstance(self.issuer, tuple) else self.issuer,
                leeway=leeway,
                options={"require": ["exp", "iat", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise OAuthError(f"{self.name}: invalid ID token ({type(exc).__name__}: {exc})") from exc
        if nonce is not None and not hmac.compare_digest(str(claims.get("nonce", "")).encode(), nonce.encode()):
            raise OAuthError(f"{self.name}: ID token nonce mismatch")
        return claims

    # -- step 3: who is this? -------------------------------------------------------------
    async def fetch_user(self, access_token: str) -> dict[str, Any]:
        if self.userinfo_url is None:
            raise OAuthError(f"{self.name} has no userinfo_url configured")
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.get(
                self.userinfo_url, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
            )
        payload = self._json(response)
        if response.is_error:
            raise OAuthError(
                f"{self.name}: userinfo request failed (HTTP {response.status_code})",
                status_code=response.status_code,
                payload=payload,
            )
        return payload

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            value = response.json()
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}

    @classmethod
    async def from_oidc_discovery(
        cls,
        issuer: str,
        *,
        name: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: tuple[str, ...] = ("openid", "email", "profile"),
        transport: httpx.AsyncBaseTransport | None = None,
        **kwargs: Any,
    ) -> OAuth2Provider:
        """Configures a provider from ``<issuer>/.well-known/openid-configuration`` (Auth0, Okta, Keycloak...)."""
        url = issuer.rstrip("/") + "/.well-known/openid-configuration"
        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.get(url)
        if response.is_error:
            raise OAuthError(
                f"OIDC discovery failed for {issuer} (HTTP {response.status_code})", status_code=response.status_code
            )
        meta = response.json()
        return cls(
            name=name,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            authorize_url=meta["authorization_endpoint"],
            token_url=meta["token_endpoint"],
            userinfo_url=meta.get("userinfo_endpoint"),
            jwks_uri=meta.get("jwks_uri"),
            issuer=meta.get("issuer"),
            scopes=scopes,
            transport=transport,
            **kwargs,
        )


def GoogleOAuth(  # noqa: N802 - reads like a class: GoogleOAuth(...)
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scopes: tuple[str, ...] = ("openid", "email", "profile"),
    **kwargs: Any,
) -> OAuth2Provider:
    return OAuth2Provider(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
        jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
        issuer=("https://accounts.google.com", "accounts.google.com"),
        scopes=scopes,
        authorize_params={"access_type": "offline", "prompt": "consent"},
        **kwargs,
    )


def GitHubOAuth(  # noqa: N802
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scopes: tuple[str, ...] = ("read:user", "user:email"),
    **kwargs: Any,
) -> OAuth2Provider:
    # GitHub doesn't support PKCE for OAuth apps' confidential clients the same way; the secret protects the exchange.
    kwargs.setdefault("use_pkce", False)
    return OAuth2Provider(
        name="github",
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        userinfo_url="https://api.github.com/user",
        scopes=scopes,
        **kwargs,
    )


def MicrosoftOAuth(  # noqa: N802
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    tenant: str = "common",
    scopes: tuple[str, ...] = ("openid", "email", "profile"),
    **kwargs: Any,
) -> OAuth2Provider:
    base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
    # Multi-tenant authorities (`common`, `organizations`, `consumers`) issue tokens whose `iss` names the user's own
    # tenant, so it can't be pinned here: check `claims["tid"]` / `claims["iss"]` yourself if you restrict sign-in.
    issuer = (
        None
        if tenant in ("common", "organizations", "consumers")
        else f"https://login.microsoftonline.com/{tenant}/v2.0"
    )
    return OAuth2Provider(
        name="microsoft",
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        authorize_url=f"{base}/authorize",
        token_url=f"{base}/token",
        userinfo_url="https://graph.microsoft.com/oidc/userinfo",
        jwks_uri=f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
        issuer=issuer,
        scopes=scopes,
        **kwargs,
    )
