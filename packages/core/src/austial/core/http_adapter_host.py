"""``HttpAdapterHost`` -- mirrors Nest's: a way to reach the HTTP platform from a provider, filter or
interceptor that is built before (or independent of) the application object.

::

    @Injectable()
    class DocsFilter:
        def __init__(self, host: HttpAdapterHost):
            self.host = host

        def on_module_init(self):
            fastapi_app = self.host.http_adapter       # the FastAPI instance
"""

from __future__ import annotations

from typing import Any


class HttpAdapterHost:
    def __init__(self) -> None:
        self.http_adapter: Any = None  # the FastAPI app once an application wraps this container
