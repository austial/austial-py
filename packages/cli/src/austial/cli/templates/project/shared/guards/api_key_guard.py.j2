import os

from austial import CanActivate, ExecutionContext


class ApiKeyGuard(CanActivate):
    """Demo guard -- protects a route with a static ``x-api-key`` header,
    the value coming from the ``API_KEY`` environment variable."""

    async def can_activate(self, context: ExecutionContext) -> bool:
        request = context.get_request()
        expected = os.getenv("API_KEY", "changeme")
        return request.headers.get("x-api-key") == expected
