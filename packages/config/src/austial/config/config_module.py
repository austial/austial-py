"""``ConfigModule`` -- mirrors ``@nestjs/config``'s ``ConfigModule.forRoot()``."""

from __future__ import annotations

import os

from austial.common.decorators.modules import Module
from austial.config.config_service import ConfigService
from austial.core.dynamic_module import DynamicModule


@Module()
class ConfigModule:
    """Import via ``ConfigModule.for_root()`` in ``AppModule``'s ``imports=[...]``,
    exactly like Nest's ``ConfigModule.forRoot()``."""

    @staticmethod
    def for_root(env_file: str = ".env", *, is_global: bool = True) -> DynamicModule:
        try:
            from dotenv import load_dotenv

            load_dotenv(env_file, override=False)
        except ImportError:  # pragma: no cover - python-dotenv ships with pydantic-settings
            pass

        service = ConfigService(dict(os.environ))
        return DynamicModule(
            module=ConfigModule,
            providers=[{"provide": ConfigService, "useValue": service}],
            exports=[ConfigService],
        )
