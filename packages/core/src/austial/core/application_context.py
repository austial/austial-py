"""``AustialApplicationContext`` -- the part of an application that doesn't need HTTP: the DI
container, lifecycle hooks and shutdown handling. Mirrors Nest's ``INestApplicationContext``
(what ``NestFactory.createApplicationContext()`` returns, and what ``NestApplication`` extends).

Use it for CLIs, workers and one-off scripts that want the module graph without a web server::

    ctx = await AustialFactory.create_application_context(AppModule)
    await ctx.get(ReportsService).run_nightly()
    await ctx.close()
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal as signal_module
from typing import Any

from austial.common.logger import Logger
from austial.core.container import Container
from austial.core.module_ref import ModuleRef
from austial.core.request_context import ContextId


class AustialApplicationContext:
    # An ASGI server owns SIGINT/SIGTERM and ends the app through the lifespan protocol (which
    # always runs shutdown hooks), so `AustialApplication` turns signal handling off.
    _owns_signals = True

    def __init__(self, container: Container):
        self._container = container
        self._initialized = False
        self._shutdown_signals: tuple[str, ...] = ()
        self._closing = False

    # -- providers --------------------------------------------------------------------
    def get(self, token: Any) -> Any:
        """Fetches a resolved provider straight out of the DI container,
        mirroring Nest's ``app.get(Token)``."""
        return self._container.resolve(token)

    def resolve(self, token: Any, context_id: ContextId | None = None) -> Any:
        """Like :meth:`get`, but also works for request-scoped providers (built inside
        ``context_id``, or a fresh one) -- mirrors Nest's ``app.resolve(Token)``."""
        return self._container.resolve(ModuleRef).resolve(token, context_id)

    # -- lifecycle --------------------------------------------------------------------
    async def init(self) -> AustialApplicationContext:
        """Runs ``on_module_init`` then ``on_application_bootstrap`` on every provider that
        defines them. Idempotent."""
        if not self._initialized:
            self._initialized = True
            self._install_signal_handlers()
            Logger.flush()
            await self._container.init_async_providers()
            await self._container.lifecycle.run_init()
        return self

    async def close(self, signal: str | None = None) -> None:
        """Runs ``on_module_destroy``, ``before_application_shutdown`` and
        ``on_application_shutdown`` (dependencies last). A no-op if never initialised."""
        if not self._initialized:
            return
        self._initialized = False
        await self._container.lifecycle.run_destroy(signal)
        self._container.lifecycle.reset()

    def enable_shutdown_hooks(self, *signals: str) -> AustialApplicationContext:
        """Closes the context (running the shutdown hooks) when the process gets one of
        ``signals`` (default ``SIGTERM`` and ``SIGINT``), then re-raises it. Takes effect on
        :meth:`init`. Under ``uvicorn``/``austial serve`` this isn't needed: the server turns
        its own signals into an ASGI lifespan shutdown, which always runs the hooks."""
        self._shutdown_signals = signals or ("SIGTERM", "SIGINT")
        if self._initialized:
            self._install_signal_handlers()
        return self

    def _install_signal_handlers(self) -> None:
        if not (self._owns_signals and self._shutdown_signals):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        for name in self._shutdown_signals:
            sig = getattr(signal_module, name)
            # add_signal_handler is unavailable off the main thread / on Windows -- then it's a no-op.
            with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                loop.add_signal_handler(sig, self._schedule_close, sig, name)

    def _schedule_close(self, sig: signal_module.Signals, name: str) -> None:
        asyncio.ensure_future(self._on_signal(sig, name))

    async def _on_signal(self, sig: signal_module.Signals, name: str) -> None:
        if self._closing:
            return
        self._closing = True
        await self.close(name)
        asyncio.get_running_loop().remove_signal_handler(sig)
        os.kill(os.getpid(), sig)  # hand the signal back so the process still terminates
