"""``register_as`` -- mirrors ``registerAs`` from ``@nestjs/config``: a namespaced configuration factory."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


class ConfigFactory:
    """A named configuration namespace built by a function.

    ::

        database_config = register_as("database", lambda: {"host": os.environ.get("DB_HOST", "localhost")})

        ConfigModule.for_root(load=[database_config])
        config.get("database.host")
        class Repo:
            def __init__(self, db=Inject(database_config.KEY)): ...      # the whole dict

    The function may take the config environment as its single argument instead of reading
    ``os.environ``.
    """

    def __init__(self, namespace: str, factory: Callable[..., Any]):
        self.namespace = namespace
        self._factory = factory
        self.KEY = f"CONFIGURATION({namespace})"

    def build(self, env: dict[str, Any]) -> Any:
        parameters = inspect.signature(self._factory).parameters
        return self._factory(env) if parameters else self._factory()

    def __call__(self, env: dict[str, Any] | None = None) -> Any:
        import os

        return self.build(env if env is not None else dict(os.environ))

    def __repr__(self) -> str:  # pragma: no cover
        return f"ConfigFactory({self.namespace!r})"


def register_as(namespace: str, factory: Callable[..., Any]) -> ConfigFactory:
    return ConfigFactory(namespace, factory)
