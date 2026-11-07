"""Protocol features, live: plain WebSockets, GraphQL (queries, mutations, subscriptions), OpenAPI and a complete
OpenID Connect login against a real identity-provider server on a real port. No mocks of the transport."""

import asyncio
import base64
import json
import time
import urllib.parse
from collections.abc import AsyncGenerator

import httpx
import jwt
import strawberry
import websockets
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Form
from fastapi.responses import RedirectResponse
from strawberry.types import Info

from austial import AustialFactory, Controller, Cookies, Get, Injectable, Module, Res
from austial.auth import OAuth2Provider, OAuthError, verify_state
from austial.graphql import GraphQLModule, inject
from austial.openapi import ApiOperation, ApiTags, DocumentBuilder, SwaggerModule
from austial.websockets import (
    ConnectedSocket,
    MessageBody,
    SubscribeMessage,
    WebSocketGateway,
    WebSocketsModule,
    WsClient,
    WsServer,
)
from integration.live import free_port, serve

# -- plain WebSockets -----------------------------------------------------------------------------


@WebSocketGateway("/chat")
@Injectable()
class Chat:
    server: WsServer

    async def handle_connection(self, client: WsClient) -> None:
        await client.send("welcome", {"id_len": len(client.id)})

    @SubscribeMessage("join")
    async def join(self, room: str = MessageBody("room"), client: WsClient = ConnectedSocket()):
        await client.join(room)
        await self.server.to(room).emit("joined", {"room": room})

    @SubscribeMessage("say")
    async def say(self, room: str = MessageBody("room"), text: str = MessageBody("text")):
        await self.server.to(room).emit("said", text)

    @SubscribeMessage("echo")
    def echo(self, data):
        return {"echo": data}


async def test_plain_websocket_gateway_with_rooms_over_a_real_socket() -> None:
    @Module(imports=[WebSocketsModule.for_root()], providers=[Chat])
    class App:
        pass

    async with serve(AustialFactory.create(App)) as base:
        url = base.replace("http", "ws") + "/chat"
        async with websockets.connect(url) as alice, websockets.connect(url) as bob:
            assert json.loads(await alice.recv())["event"] == "welcome"
            assert json.loads(await bob.recv())["event"] == "welcome"
            await alice.send(json.dumps({"event": "echo", "data": {"n": 1}, "id": 7}))
            reply = json.loads(await alice.recv())
            assert reply["event"] == "echo" and reply["data"] == {"echo": {"n": 1}} and reply["id"] == 7
            await alice.send(json.dumps({"event": "join", "data": {"room": "r"}}))
            assert json.loads(await alice.recv())["event"] == "joined"
            await bob.send(json.dumps({"event": "say", "data": {"room": "r", "text": "hi"}}))
            assert json.loads(await alice.recv()) == {"event": "said", "data": "hi"}  # alice is in the room
            await bob.send(json.dumps({"event": "nope"}))
            assert json.loads(await bob.recv())["event"] == "exception"  # unknown event: error, connection alive
            await bob.send("not json")
            assert json.loads(await bob.recv())["event"] == "exception"
            await bob.send(json.dumps({"event": "echo", "data": 2}))
            assert json.loads(await bob.recv())["data"] == {"echo": 2}


# -- GraphQL ----------------------------------------------------------------------------------------


@Injectable()
class Greeter:
    def greet(self, name: str) -> str:
        return f"Hello, {name}!"


@strawberry.type
class Query:
    @strawberry.field
    def greeting(self, info: Info, name: str = "world") -> str:
        return inject(info, Greeter).greet(name)


@strawberry.type
class Mutation:
    @strawberry.mutation
    def shout(self, info: Info, text: str) -> str:
        return inject(info, Greeter).greet(text).upper()


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def count(self, info: Info, to: int = 3) -> AsyncGenerator[str, None]:
        for n in range(to):
            yield inject(info, Greeter).greet(str(n))
            await asyncio.sleep(0.01)


async def test_graphql_queries_mutations_and_subscriptions_over_real_sockets() -> None:
    schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)

    @Module(imports=[GraphQLModule.for_root(schema=schema)], providers=[Greeter])
    class App:
        pass

    async with serve(AustialFactory.create(App)) as base, httpx.AsyncClient(base_url=base) as c:
        q = await c.post("/graphql", json={"query": '{ greeting(name: "Ada") }'})
        assert q.json() == {"data": {"greeting": "Hello, Ada!"}}
        m = await c.post("/graphql", json={"query": 'mutation { shout(text: "hey") }'})
        assert m.json() == {"data": {"shout": "HELLO, HEY!"}}
        bad = await c.post("/graphql", json={"query": "{ nope }"})
        assert "errors" in bad.json()

        ws_url = base.replace("http", "ws") + "/graphql"
        async with websockets.connect(ws_url, subprotocols=[websockets.Subprotocol("graphql-transport-ws")]) as ws:
            await ws.send(json.dumps({"type": "connection_init"}))
            assert json.loads(await ws.recv())["type"] == "connection_ack"
            await ws.send(
                json.dumps({"id": "1", "type": "subscribe", "payload": {"query": "subscription { count(to: 3) }"}})
            )
            values = []
            while True:
                message = json.loads(await ws.recv())
                if message["type"] == "complete":
                    break
                values.append(message["payload"]["data"]["count"])
            assert values == ["Hello, 0!", "Hello, 1!", "Hello, 2!"]


# -- OpenAPI ----------------------------------------------------------------------------------------


@ApiTags("cats")
@Controller("cats")
class Cats:
    @Get(":id")
    @ApiOperation(summary="Find one cat")
    def one(self, id: int):
        return {"id": id}


async def test_openapi_document_and_ui_are_served() -> None:
    @Module(controllers=[Cats])
    class App:
        pass

    app = AustialFactory.create(App)
    SwaggerModule.setup(app, DocumentBuilder().set_title("Cats API").set_version("1.0").build(), path="api-docs")
    async with serve(app) as base, httpx.AsyncClient(base_url=base) as c:
        document = (await c.get("/api-docs-json")).json()
        assert document["info"]["title"] == "Cats API"
        operation = document["paths"]["/cats/{id}"]["get"]
        assert operation["summary"] == "Find one cat" and operation["tags"] == ["cats"]
        assert "swagger" in (await c.get("/api-docs")).text.lower()


# -- OpenID Connect against a live identity provider ---------------------------------------------


def _b64(number: int) -> str:
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def fake_identity_provider(issuer: str, client_id: str):
    """A minimal OIDC provider (discovery, authorize, token, JWKS, userinfo) signing ID tokens with a real RSA key."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    jwk = {"kty": "RSA", "kid": "k1", "use": "sig", "alg": "RS256", "n": _b64(numbers.n), "e": _b64(numbers.e)}
    codes: dict[str, dict] = {}
    idp = FastAPI()

    @idp.get("/.well-known/openid-configuration")
    def discovery():
        return {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/authorize",
            "token_endpoint": f"{issuer}/token",
            "userinfo_endpoint": f"{issuer}/userinfo",
            "jwks_uri": f"{issuer}/jwks",
        }

    @idp.get("/authorize")
    def authorize(redirect_uri: str, state: str, nonce: str, code_challenge: str, client_id: str):
        code = f"code-{len(codes)}"
        codes[code] = {"nonce": nonce, "challenge": code_challenge}
        return RedirectResponse(f"{redirect_uri}?code={code}&state={urllib.parse.quote(state)}")

    @idp.post("/token")
    def token(code: str = Form(), code_verifier: str = Form(), client_id: str = Form(), client_secret: str = Form()):
        saved = codes[code]
        expected = (
            base64.urlsafe_b64encode(__import__("hashlib").sha256(code_verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        assert expected == saved["challenge"], "PKCE verifier does not match"
        now = int(time.time())
        claims = {
            "iss": issuer,
            "aud": client_id,
            "sub": "user-42",
            "email": "ada@example.com",
            "iat": now,
            "exp": now + 300,
            "nonce": saved["nonce"],
        }
        id_token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})
        return {"access_token": "at-1", "token_type": "Bearer", "id_token": id_token, "expires_in": 300}

    @idp.get("/jwks")
    def jwks():
        return {"keys": [jwk]}

    @idp.get("/userinfo")
    def userinfo():
        return {"sub": "user-42", "email": "ada@example.com"}

    return idp, key


async def test_full_openid_connect_login_with_id_token_verification_live() -> None:
    idp_port, app_port = free_port(), free_port()
    issuer, app_url = f"http://127.0.0.1:{idp_port}", f"http://127.0.0.1:{app_port}"
    idp, key = fake_identity_provider(issuer, "client-1")

    async with serve(idp, port=idp_port):
        provider = await OAuth2Provider.from_oidc_discovery(
            issuer, name="live", client_id="client-1", client_secret="s3cret", redirect_uri=f"{app_url}/auth/callback"
        )
        sessions: dict[str, dict] = {}

        @Controller("auth")
        class AuthController:
            @Get("login")
            def login(self, response: Res):
                request = provider.authorization_url()
                sessions["s"] = {"state": request.state, "verifier": request.code_verifier, "nonce": request.nonce}
                response.set_cookie("sid", "s", httponly=True)
                return {"url": request.url}

            @Get("callback")
            async def callback(self, code: str, state: str, sid: str = Cookies("sid")):
                saved = sessions[sid]
                verify_state(saved["state"], state)
                tokens = await provider.exchange_code(code, code_verifier=saved["verifier"])
                claims = await provider.verify_id_token(tokens.id_token or "", nonce=saved["nonce"])
                profile = await provider.fetch_user(tokens.access_token)
                return {"sub": claims["sub"], "email": claims["email"], "profile": profile}

            @Get("tampered")
            async def tampered(self):
                other = rsa_key_signed_token(issuer)
                try:
                    await provider.verify_id_token(other)
                except OAuthError as exc:
                    return {"rejected": str(exc)}
                return {"rejected": None}

        def rsa_key_signed_token(iss: str) -> str:
            attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            now = int(time.time())
            claims = {"iss": iss, "aud": "client-1", "sub": "evil", "iat": now, "exp": now + 60}
            return jwt.encode(claims, attacker, algorithm="RS256", headers={"kid": "k1"})  # right kid, wrong key

        @Module(controllers=[AuthController])
        class App:
            pass

        async with (
            serve(AustialFactory.create(App), port=app_port) as base,
            httpx.AsyncClient(base_url=base, follow_redirects=False) as browser,
        ):
            start = await browser.get("/auth/login")
            authorize_url = start.json()["url"]
            # the "browser" visits the identity provider, which redirects back to the app with a code
            async with httpx.AsyncClient() as idp_client:
                redirect = await idp_client.get(authorize_url)
            assert redirect.status_code in (302, 307)
            callback = await browser.get(redirect.headers["location"])
            assert callback.json()["sub"] == "user-42" and callback.json()["email"] == "ada@example.com"
            assert callback.json()["profile"]["sub"] == "user-42"

            forged = (await browser.get("/auth/tampered")).json()
            assert forged["rejected"], "a token signed by another key must be rejected"


# -- authentication strategies over real HTTP -----------------------------------------------------


async def test_strategy_guard_with_jwt_and_api_key_over_real_http() -> None:
    from austial import UseGuards
    from austial.auth import (
        AuthConfig,
        AuthenticationError,
        AuthModule,
        AuthStrategy,
        CurrentUser,
        JwtStrategy,
        StrategyGuard,
    )

    @Injectable()
    class ApiKey(AuthStrategy):
        name = "api-key"

        async def validate(self, request):
            if request.headers.get("x-api-key") == "k-1":
                return {"owner": "service"}
            raise AuthenticationError("bad key")

    @Controller("secure")
    @UseGuards(StrategyGuard("jwt", "api-key"))
    class Secure:
        @Get()
        def who(self, user=CurrentUser()):
            return {"who": getattr(user, "subject", None) or user["owner"]}

    @Module(
        imports=[AuthModule.for_root(AuthConfig(jwt_secret="s" * 48, issuer="live"))],
        controllers=[Secure],
        providers=[ApiKey],
    )
    class App:
        pass

    app = AustialFactory.create(App)
    await app.init()
    token = app.get(JwtStrategy).sign("user-9")
    async with serve(app) as base, httpx.AsyncClient(base_url=base) as c:
        assert (await c.get("/secure", headers={"Authorization": f"Bearer {token}"})).json() == {"who": "user-9"}
        assert (await c.get("/secure", headers={"x-api-key": "k-1"})).json() == {"who": "service"}
        assert (await c.get("/secure")).status_code == 401
        assert (await c.get("/secure", headers={"Authorization": "Bearer garbage"})).status_code == 401
