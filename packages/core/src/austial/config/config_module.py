"""``ConfigModule`` -- mirrors ``@nestjs/config``'s ``ConfigModule.forRoot()`` / ``forFeature()``."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

from austial.common.decorators.modules import Module
from austial.config.config_service import ConfigService
from austial.config.registry import ConfigFactory
from austial.core.dynamic_module import DynamicModule


class ConfigValidationError(Exception):
    """The environment didn't satisfy the validation schema; ``errors`` lists each problem."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Invalid configuration:\n  - " + "\n  - ".join(errors))


_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def expand_variables(env: dict[str, str]) -> dict[str, str]:
    """Expands ``${VAR}``, ``$VAR`` and ``${VAR:-default}`` in values, using the other entries (a variable
    may reference one that itself references another). Unknown variables expand to ``""``; cycles raise."""
    resolved: dict[str, str] = {}

    def expand(key: str, stack: tuple[str, ...]) -> str:
        if key in resolved:
            return resolved[key]
        if key in stack:
            raise ValueError(f"Circular variable reference: {' -> '.join((*stack, key))}")

        def substitute(match: re.Match[str]) -> str:
            name = match.group(1) or match.group(3)
            default = match.group(2)
            if name in env:
                return expand(name, (*stack, key))
            return default if default is not None else ""

        value = _VAR.sub(substitute, env[key])
        resolved[key] = value
        return value

    return {key: expand(key, ()) for key in env}


@Module()
class ConfigModule:
    """Import via ``ConfigModule.for_root()`` in ``AppModule``'s ``imports=[...]``,
    exactly like Nest's ``ConfigModule.forRoot()``."""

    @staticmethod
    def for_root(
        env_file: str | Sequence[str] = ".env",
        *,
        is_global: bool = True,
        ignore_env_file: bool = False,
        expand: bool = False,
        validation_schema: type[BaseModel] | None = None,
        validate: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        load: Sequence[ConfigFactory] = (),
    ) -> DynamicModule:
        """
        * ``env_file`` -- one path or several; with several, the **first** file that defines a variable wins,
          and real environment variables beat them all.
        * ``expand`` -- expand ``${VAR}`` references between values (also written back to ``os.environ``).
        * ``validation_schema`` -- a pydantic model; the environment is validated (and coerced: ``PORT: int``)
          at startup and the module raises :class:`ConfigValidationError` listing every problem.
        * ``validate`` -- alternative to a schema: ``fn(env) -> env`` that may raise.
        * ``load`` -- ``register_as`` namespaces to build now.
        """
        if not ignore_env_file:
            try:
                from dotenv import load_dotenv

                for path in [env_file] if isinstance(env_file, str) else env_file:
                    load_dotenv(path, override=False)
            except ImportError:  # pragma: no cover - python-dotenv ships with pydantic-settings
                pass

        env: dict[str, Any] = dict(os.environ)
        if expand:
            env = {**env, **expand_variables({k: v for k, v in env.items() if isinstance(v, str)})}
            os.environ.update({k: v for k, v in env.items() if isinstance(v, str)})
        env = _validate(env, validation_schema, validate)

        service = ConfigService(env)
        for factory in load:
            service.register_namespace(factory)
        return DynamicModule(
            module=ConfigModule,
            providers=[
                {"provide": ConfigService, "useValue": service},
                *({"provide": f.KEY, "useValue": service.get(f)} for f in load),
            ],
            exports=[ConfigService, *(f.KEY for f in load)],
        )

    @staticmethod
    def for_feature(factory: ConfigFactory) -> DynamicModule:
        """Registers one more ``register_as`` namespace from a feature module, like ``forFeature()``. The
        namespace is built when the application initialises (``config.get("ns.key")``) and injectable
        straight away as ``Inject(factory.KEY)``."""

        class FeatureLoader:
            def __init__(self, config: ConfigService):
                self.config = config

            def on_module_init(self) -> None:
                # Eager, so `config.get("ns.key")` works without anything having injected the namespace.
                self.config.register_namespace(factory)

        return DynamicModule(
            module=ConfigModule,
            providers=[
                FeatureLoader,
                {
                    "provide": factory.KEY,
                    "useFactory": lambda config: config.register_namespace(factory),
                    "inject": [ConfigService],
                },
            ],
            exports=[factory.KEY],
        )


def _validate(
    env: dict[str, Any],
    schema: type[BaseModel] | None,
    validate: Callable[[dict[str, Any]], dict[str, Any]] | None,
) -> dict[str, Any]:
    if schema is not None:
        try:
            validated = schema.model_validate(env)
        except ValidationError as exc:
            raise ConfigValidationError(
                [f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}" for e in exc.errors()]
            ) from exc
        env = {**env, **validated.model_dump()}
    if validate is not None:
        try:
            env = validate(env)
        except ConfigValidationError:
            raise
        except Exception as exc:
            raise ConfigValidationError([str(exc)]) from exc
    return env
