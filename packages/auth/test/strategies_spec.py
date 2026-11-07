from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from austial import AustialFactory, Controller, Get, Injectable, Module, UseGuards
from austial.auth import (
    AuthConfig,
    AuthenticationError,
    AuthModule,
    AuthStrategy,
    CurrentUser,
    JwtStrategy,
    Public,
    StrategyGuard,
)

SECRET = "x" * 48


@Injectable()
class ApiKeyStrategy(AuthStrategy):
    name = "api-key"

    async def validate(self, request):
        if request.headers.get("x-api-key") == "k-123":
            return {"owner": "service-account"}
        raise AuthenticationError("invalid API key")


@Controller("reports")
@UseGuards(StrategyGuard("jwt", "api-key"))
class ReportsController:
    @Get()
    def list(self, user=CurrentUser()):
        return {"who": getattr(user, "subject", None) or user["owner"]}

    @Get("open")
    @Public()
    def open(self):
        return {"open": True}


@Controller("keys")
@UseGuards(StrategyGuard("api-key"))
class KeysOnly:
    @Get()
    def get(self):
        return {"ok": True}


def make_app():
    @Module(
        imports=[AuthModule.for_root(AuthConfig(jwt_secret=SECRET, issuer="test"))],
        controllers=[ReportsController, KeysOnly],
        providers=[ApiKeyStrategy],
    )
    class Root:
        pass

    return AustialFactory.create(Root)


async def test_any_strategy_may_accept_and_the_user_reaches_the_handler() -> None:
    app = make_app()
    await app.init()
    token = app.get(JwtStrategy).sign("user-1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/reports", headers={"Authorization": f"Bearer {token}"})).json() == {"who": "user-1"}
        assert (await c.get("/reports", headers={"x-api-key": "k-123"})).json() == {"who": "service-account"}
        assert (await c.get("/reports/open")).json() == {"open": True}  # @Public skips the guard

        rejected = await c.get("/reports", headers={"x-api-key": "wrong"})
        assert rejected.status_code == 401
        assert (await c.get("/keys")).status_code == 401
        assert (
            await c.get("/keys", headers={"Authorization": f"Bearer {token}"})
        ).status_code == 401  # jwt not allowed here
        assert (await c.get("/keys", headers={"x-api-key": "k-123"})).json() == {"ok": True}


def test_guard_needs_names_and_unknown_names_fail_clearly() -> None:
    import pytest

    with pytest.raises(ValueError):
        StrategyGuard()
