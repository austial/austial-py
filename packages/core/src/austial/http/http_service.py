"""``HttpService`` -- mirrors ``@nestjs/axios``'s ``HttpService``, over ``httpx``.

::

    @Injectable()
    class WeatherService:
        def __init__(self, http: HttpService):
            self.http = http

        async def forecast(self, city: str) -> dict:
            response = await self.http.get("/forecast", params={"city": city})
            return response.json()
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from austial.common.decorators.injectable import Inject

HTTP_OPTIONS = "AUSTIAL_HTTP_OPTIONS"
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})


@dataclass
class HttpModuleOptions:
    base_url: str = ""
    timeout: float | None = 5.0  # seconds, for connect/read/write/pool; None disables
    headers: Mapping[str, str] = field(default_factory=dict)
    follow_redirects: bool = True
    raise_for_status: bool = True  # non-2xx raises HttpStatusError (like axios), instead of returning the response
    retries: int = 0  # extra attempts after the first
    retry_statuses: Sequence[int] = (502, 503, 504)
    retry_backoff: float = 0.2  # seconds; doubles each attempt
    retry_non_idempotent: bool = False  # also retry POST/PATCH
    transport: httpx.AsyncBaseTransport | None = None  # swap the network layer (tests, proxies)


class HttpStatusError(Exception):
    """The server answered with a non-2xx status and ``raise_for_status`` is on."""

    def __init__(self, response: httpx.Response):
        self.response = response
        self.status_code = response.status_code
        super().__init__(f"{response.request.method} {response.request.url} -> {response.status_code}")


def _as_async(hook: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """httpx's async client awaits every hook, so adapt plain functions."""

    async def wrapper(arg: Any) -> None:
        result = hook(arg)
        if inspect.isawaitable(result):
            await result

    return wrapper


class HttpService:
    def __init__(self, options: HttpModuleOptions = Inject(HTTP_OPTIONS)):
        self.options = options or HttpModuleOptions()
        self.client = httpx.AsyncClient(
            base_url=self.options.base_url,
            timeout=self.options.timeout,
            headers=dict(self.options.headers),
            follow_redirects=self.options.follow_redirects,
            transport=self.options.transport,
        )

    # -- interceptors (httpx event hooks; may be sync or async) -----------------------
    def add_request_interceptor(self, hook: Callable[[httpx.Request], Any]) -> None:
        """``hook(request)`` runs before each request is sent and may mutate it (add auth, trace ids...)."""
        self.client.event_hooks["request"].append(_as_async(hook))

    def add_response_interceptor(self, hook: Callable[[httpx.Response], Any]) -> None:
        """``hook(response)`` runs on every response before it is returned (log, record metrics...)."""
        self.client.event_hooks["response"].append(_as_async(hook))

    # -- requests ---------------------------------------------------------------------
    async def request(
        self,
        method: str,
        url: str,
        *,
        raise_for_status: bool | None = None,
        retries: int | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Sends a request and returns the ``httpx.Response``. ``kwargs`` go to ``httpx`` (``params``, ``json``,
        ``data``, ``headers``, ``timeout``...). Retries transport errors and ``retry_statuses`` with exponential
        backoff, for idempotent methods unless ``retry_non_idempotent``."""
        method = method.upper()
        attempts = 1 + (self.options.retries if retries is None else retries)
        if method not in IDEMPOTENT_METHODS and not self.options.retry_non_idempotent:
            attempts = 1
        check = self.options.raise_for_status if raise_for_status is None else raise_for_status

        last_error: Exception | None = None
        for attempt in range(attempts):
            if attempt:
                await asyncio.sleep(self.options.retry_backoff * 2 ** (attempt - 1))
            try:
                response = await self.client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                last_error = exc
                continue
            if response.status_code in self.options.retry_statuses and attempt < attempts - 1:
                continue
            if check and response.is_error:
                raise HttpStatusError(response)
            return response
        assert last_error is not None
        raise last_error

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def head(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("HEAD", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PATCH", url, **kwargs)

    async def on_module_destroy(self) -> None:
        await self.client.aclose()
