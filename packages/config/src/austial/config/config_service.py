"""``ConfigService`` -- mirrors ``@nestjs/config``'s ``ConfigService``."""

from __future__ import annotations

import os
from typing import Any

from austial.common.decorators.injectable import Injectable


@Injectable()
class ConfigService:
    def __init__(self, env: dict | None = None):
        self._env = env if env is not None else dict(os.environ)

    def get(self, key: str, default: Any = None) -> Any:
        return self._env.get(key, default)

    def get_or_throw(self, key: str) -> Any:
        if key not in self._env:
            raise KeyError(f"Configuration key '{key}' is not defined")
        return self._env[key]
