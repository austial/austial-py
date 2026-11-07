"""``ConfigService`` -- mirrors ``@nestjs/config``'s ``ConfigService``."""

from __future__ import annotations

import os
from typing import Any

from austial.common.decorators.injectable import Injectable
from austial.config.registry import ConfigFactory

_MISSING = object()


@Injectable()
class ConfigService:
    """Reads configuration: environment variables (plus validated/expanded values) and namespaced
    values built by ``register_as`` factories.

    ``get("PORT")`` reads a variable; ``get("database.host")`` reads ``host`` from the ``database``
    namespace; ``get(database_config)`` returns the whole namespace. A literal key wins over a dotted path.
    """

    def __init__(self, env: dict | None = None):
        self._env: dict[str, Any] = env if env is not None else dict(os.environ)
        self._namespaces: dict[str, Any] = {}

    # -- namespaces -------------------------------------------------------------------
    def register_namespace(self, factory: ConfigFactory) -> Any:
        """Builds a ``register_as`` factory once and files its result under its namespace."""
        if factory.namespace not in self._namespaces:
            self._namespaces[factory.namespace] = factory.build(self._env)
        return self._namespaces[factory.namespace]

    # -- reading ----------------------------------------------------------------------
    def _lookup(self, key: str) -> Any:
        if key in self._env:
            return self._env[key]
        head, _, rest = key.partition(".")
        if head in self._namespaces:
            value: Any = self._namespaces[head]
            for part in rest.split(".") if rest else []:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                elif hasattr(value, part):
                    value = getattr(value, part)
                else:
                    return _MISSING
            return value
        return _MISSING

    def get(self, key: str | ConfigFactory, default: Any = None) -> Any:
        if isinstance(key, ConfigFactory):
            return self._namespaces.get(key.namespace, default)
        value = self._lookup(key)
        return default if value is _MISSING else value

    def get_or_throw(self, key: str | ConfigFactory) -> Any:
        if isinstance(key, ConfigFactory):
            if key.namespace not in self._namespaces:
                raise KeyError(f"Configuration namespace '{key.namespace}' is not registered")
            return self._namespaces[key.namespace]
        value = self._lookup(key)
        if value is _MISSING:
            raise KeyError(f"Configuration key '{key}' is not defined")
        return value

    def has(self, key: str) -> bool:
        return self._lookup(key) is not _MISSING

    def set(self, key: str, value: Any) -> None:
        """Overrides a value for this service (the process environment is untouched)."""
        self._env[key] = value

    def get_all(self) -> dict[str, Any]:
        return {**self._env, **{ns: value for ns, value in self._namespaces.items()}}
