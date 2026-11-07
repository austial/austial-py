from __future__ import annotations

import httpx
import pytest

from austial import AustialFactory, Module
from austial.http import HttpModule, HttpModuleOptions, HttpService, HttpStatusError
from austial.testing import Test


def mock(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def _service(handler, **options) -> HttpService:
    module = await Test.create_testing_module(
        imports=[HttpModule.register(transport=mock(handler), retry_backoff=0, **options)]
    ).compile()
    return module.get(HttpService)


async def test_verbs_base_url_headers_and_json() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"method": request.method, "path": request.url.path})

    http = await _service(handler, base_url="https://api.example.com/v1", headers={"X-Key": "k"})
    assert (await http.get("/things", params={"a": "1"})).json() == {"method": "GET", "path": "/v1/things"}
    for verb in ("post", "put", "patch", "delete", "head"):
        response = await getattr(http, verb)("/things")
        assert response.status_code == 200
    created = await http.post("/things", json={"name": "n"})
    assert created.status_code == 200
    assert seen[0].headers["x-key"] == "k" and seen[0].url.params["a"] == "1"
    assert seen[-1].content == b'{"name":"n"}'


async def test_non_2xx_raises_by_default_and_can_be_disabled() -> None:
    http = await _service(lambda r: httpx.Response(404, json={"error": "nope"}))
    with pytest.raises(HttpStatusError) as caught:
        await http.get("http://x/missing")
    assert caught.value.status_code == 404 and caught.value.response.json() == {"error": "nope"}
    assert "GET" in str(caught.value) and "404" in str(caught.value)

    assert (await http.get("http://x/missing", raise_for_status=False)).status_code == 404
    lenient = await _service(lambda r: httpx.Response(500), raise_for_status=False)
    assert (await lenient.get("http://x")).status_code == 500


async def test_retries_on_5xx_and_transport_errors_with_idempotency_rules() -> None:
    attempts = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(200, text="ok") if attempts["n"] >= 3 else httpx.Response(503)

    http = await _service(flaky, retries=3)
    assert (await http.get("http://x")).text == "ok" and attempts["n"] == 3

    attempts["n"] = 0
    post = await _service(lambda r: (attempts.update(n=attempts["n"] + 1), httpx.Response(503))[1], retries=3)
    with pytest.raises(HttpStatusError):
        await post.post("http://x")
    assert attempts["n"] == 1  # POST isn't retried unless asked to

    attempts["n"] = 0
    risky = await _service(
        lambda r: (attempts.update(n=attempts["n"] + 1), httpx.Response(503))[1], retries=2, retry_non_idempotent=True
    )
    with pytest.raises(HttpStatusError):
        await risky.post("http://x")
    assert attempts["n"] == 3

    errors = {"n": 0}

    def boom(request: httpx.Request) -> httpx.Response:
        errors["n"] += 1
        raise httpx.ConnectError("refused")

    down = await _service(boom, retries=2)
    with pytest.raises(httpx.ConnectError):
        await down.get("http://x")
    assert errors["n"] == 3
    assert (await _service(lambda r: httpx.Response(200), retries=0)).options.retries == 0
    override = await _service(boom, retries=0)
    with pytest.raises(httpx.ConnectError):
        await override.get("http://x", retries=1)  # per-call override


async def test_request_and_response_interceptors_sync_and_async() -> None:
    log: list[str] = []
    http = await _service(lambda r: httpx.Response(200, headers={"x-seen": r.headers.get("authorization", "-")}))

    def add_auth(request: httpx.Request) -> None:
        request.headers["authorization"] = "Bearer t"

    async def trace(response: httpx.Response) -> None:
        log.append(f"{response.status_code}")

    http.add_request_interceptor(add_auth)
    http.add_response_interceptor(trace)
    response = await http.get("http://x")
    assert response.headers["x-seen"] == "Bearer t" and log == ["200"]


async def test_register_async_and_client_closes_on_destroy() -> None:
    module = await Test.create_testing_module(
        imports=[
            HttpModule.register_async(
                use_factory=lambda: HttpModuleOptions(transport=mock(lambda r: httpx.Response(204)))
            )
        ]
    ).compile()
    http = module.get(HttpService)
    assert (await http.get("http://x")).status_code == 204
    app = module.create_austial_application()
    await app.init()
    await module.close()
    assert http.client.is_closed


async def test_module_in_a_real_app_graph() -> None:
    @Module(imports=[HttpModule.register(transport=mock(lambda r: httpx.Response(200)))])
    class Root:
        pass

    app = AustialFactory.create(Root)
    assert isinstance(app.get(HttpService), HttpService)
