"""Lifecycle hook interfaces -- mirrors ``@nestjs/common``'s ``OnModuleInit`` & friends.

Implementing them is optional: the framework finds hooks by method name, so a provider that
simply defines ``async def on_module_init(self)`` gets called too. Subclassing the interface
just makes the intent explicit and lets type-checkers verify the signature. Every hook may be
a plain method or a coroutine.

Order, for ``await app.init()`` (or ASGI lifespan startup)::

    on_module_init  ->  on_application_bootstrap

and for ``await app.close()`` (or lifespan shutdown / a signal with ``enable_shutdown_hooks``),
dependencies last::

    on_module_destroy  ->  before_application_shutdown  ->  on_application_shutdown
"""

from __future__ import annotations

from abc import ABC, abstractmethod

ON_MODULE_INIT = "on_module_init"
ON_APPLICATION_BOOTSTRAP = "on_application_bootstrap"
ON_MODULE_DESTROY = "on_module_destroy"
BEFORE_APPLICATION_SHUTDOWN = "before_application_shutdown"
ON_APPLICATION_SHUTDOWN = "on_application_shutdown"

LIFECYCLE_HOOKS = (
    ON_MODULE_INIT,
    ON_APPLICATION_BOOTSTRAP,
    ON_MODULE_DESTROY,
    BEFORE_APPLICATION_SHUTDOWN,
    ON_APPLICATION_SHUTDOWN,
)


class OnModuleInit(ABC):
    """Called once the host module's dependencies have been resolved."""

    @abstractmethod
    def on_module_init(self) -> object:
        raise NotImplementedError


class OnApplicationBootstrap(ABC):
    """Called once every module has been initialised, before the app starts serving."""

    @abstractmethod
    def on_application_bootstrap(self) -> object:
        raise NotImplementedError


class OnModuleDestroy(ABC):
    """Called when the application is closing, before connections are torn down."""

    @abstractmethod
    def on_module_destroy(self) -> object:
        raise NotImplementedError


class BeforeApplicationShutdown(ABC):
    """Called after ``on_module_destroy``; receives the signal name if one triggered shutdown."""

    @abstractmethod
    def before_application_shutdown(self, signal: str | None = None) -> object:
        raise NotImplementedError


class OnApplicationShutdown(ABC):
    """Called last, once connections have closed; receives the signal name if one triggered shutdown."""

    @abstractmethod
    def on_application_shutdown(self, signal: str | None = None) -> object:
        raise NotImplementedError
