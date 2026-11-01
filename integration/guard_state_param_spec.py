"""Regression test: a handler parameter bound via ``FromRequestState`` (the mechanism behind
``austial.auth.CurrentUser()``) must see a value a *guard* wrote to ``request.state`` during
*this* request -- not an empty state resolved before the guard loop ran.

Before the fix, ``RouterBuilder`` let FastAPI resolve every ``Depends``-shaped default (including
one built from ``FromRequestState``) as an ordinary dependency, which happens before the guard
loop inside the endpoint wrapper even runs -- so the parameter was always ``None``, no matter what
a guard set. This never surfaced in a plain unit test of the guard or of the param helper alone;
it only shows up in a real, wired end-to-end request, which is why this lives in ``integration/``.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from austial import CanActivate, Controller, ExecutionContext, Get, UseGuards
from austial.common import FromRequestState
from austial.testing import Test


class StampPrincipalGuard(CanActivate):
    """Stands in for ``AuthGuard``: writes to ``request.state`` the way a real auth guard would."""

    async def can_activate(self, context: ExecutionContext) -> bool:
        context.get_request().state.principal = "alice"
        return True


@Controller("whoami")
class WhoAmIController:
    @Get("guarded")
    @UseGuards(StampPrincipalGuard)
    async def guarded(self, principal: str | None = FromRequestState("principal")) -> dict:
        return {"principal": principal}

    @Get("unguarded")
    async def unguarded(self, principal: str | None = FromRequestState("principal", default="anonymous")) -> dict:
        return {"principal": principal}


@pytest.mark.asyncio
async def test_guard_state_param_sees_the_value_the_guard_just_wrote():
    module = await Test.create_testing_module(controllers=[WhoAmIController]).compile()
    app = module.create_austial_application()
    await app.init()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        guarded = await client.get("/whoami/guarded")
        assert guarded.status_code == 200
        assert guarded.json() == {"principal": "alice"}


@pytest.mark.asyncio
async def test_guard_state_param_falls_back_to_its_default_when_no_guard_set_it():
    module = await Test.create_testing_module(controllers=[WhoAmIController]).compile()
    app = module.create_austial_application()
    await app.init()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        unguarded = await client.get("/whoami/unguarded")
        assert unguarded.status_code == 200
        assert unguarded.json() == {"principal": "anonymous"}


@pytest.mark.asyncio
async def test_guard_state_param_is_absent_from_the_openapi_schema():
    """It never comes from the wire, so it must not appear as a request parameter."""
    module = await Test.create_testing_module(controllers=[WhoAmIController]).compile()
    app = module.create_austial_application()
    await app.init()

    schema = app.get_http_adapter().openapi()
    guarded_params = schema["paths"]["/whoami/guarded"]["get"].get("parameters", [])
    assert guarded_params == []
