"""The DI container -- mirrors Nest's ``IoC`` container.

Providers are resolved from constructor type hints, recursively, with a
singleton cache by default (``Scope.TRANSIENT`` opts a provider out of
caching). Supports Nest's three "custom provider" shapes as plain dicts:
``{"provide": TOKEN, "useValue": ...}``, ``{"provide": TOKEN, "useClass": ...}``,
``{"provide": TOKEN, "useFactory": fn, "inject": [...]}``.
"""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from austial.common.decorators.injectable import InjectMarker, OptionalMarker
from austial.common.enums import Scope
from austial.core.metadata import INJECTABLE_METADATA, get_metadata

_UNSET = object()


class ProviderNotFoundError(Exception):
    def __init__(self, token: Any):
        name = getattr(token, "__name__", token)
        super().__init__(
            f"Nest can't resolve dependency '{name}'. Is it registered in a "
            f"module's `providers=[...]` (or `exports=[...]` of an imported module)?"
        )
        self.token = token


class CircularDependencyError(Exception):
    def __init__(self, token: Any):
        name = getattr(token, "__name__", token)
        super().__init__(f"Circular dependency detected while resolving '{name}'.")


@dataclass
class ProviderDefinition:
    token: Any
    use_class: type | None = None
    use_value: Any = _UNSET
    use_factory: Callable | None = None
    inject: Sequence[Any] = field(default_factory=list)
    scope: Scope = Scope.DEFAULT


class Container:
    """One container per application. Every module's providers/controllers
    register into the same container (Nest's DI graph is application-wide
    too, scoped by module `exports`/`imports` only at the *visibility* level,
    which Austial does not currently enforce for simplicity)."""

    def __init__(self):
        self._definitions: dict[Any, ProviderDefinition] = {}
        self._singletons: dict[Any, Any] = {}

    def register(self, provider: Any) -> ProviderDefinition:
        definition = self._normalize(provider)
        self._definitions[definition.token] = definition
        return definition

    def has(self, token: Any) -> bool:
        return token in self._definitions or token in self._singletons

    def set_instance(self, token: Any, instance: Any) -> None:
        """Registers an already-built instance under `token` (used for
        controllers, which the router builder constructs itself)."""
        self._singletons[token] = instance
        self._definitions.setdefault(token, ProviderDefinition(token=token, use_value=instance))

    def _normalize(self, provider: Any) -> ProviderDefinition:
        if isinstance(provider, dict):
            token = provider["provide"]
            if "useValue" in provider:
                return ProviderDefinition(token=token, use_value=provider["useValue"])
            if "useClass" in provider:
                use_class = provider["useClass"]
                scope = get_metadata(INJECTABLE_METADATA, use_class, {}).get("scope", Scope.DEFAULT)
                return ProviderDefinition(token=token, use_class=use_class, scope=scope)
            if "useFactory" in provider:
                return ProviderDefinition(
                    token=token, use_factory=provider["useFactory"], inject=provider.get("inject", [])
                )
            raise ValueError(f"Invalid provider definition: {provider!r}")
        # Plain class shorthand, e.g. `providers=[HealthService]`.
        scope = get_metadata(INJECTABLE_METADATA, provider, {}).get("scope", Scope.DEFAULT)
        return ProviderDefinition(token=provider, use_class=provider, scope=scope)

    def resolve(self, token: Any, *, _resolving: frozenset = frozenset()) -> Any:
        if token in self._singletons:
            return self._singletons[token]

        definition = self._definitions.get(token)
        if definition is None:
            if isinstance(token, type):
                # Auto-register unregistered `@Injectable` classes encountered
                # only as a nested constructor dependency -- keeps things
                # working even if a provider was forgotten in `providers=[]`.
                definition = self.register(token)
            else:
                raise ProviderNotFoundError(token)

        if token in _resolving:
            raise CircularDependencyError(token)
        next_resolving = _resolving | {token}

        instance = self._instantiate(definition, next_resolving)
        if definition.scope == Scope.DEFAULT:
            self._singletons[token] = instance
        return instance

    def _instantiate(self, definition: ProviderDefinition, resolving: frozenset) -> Any:
        if definition.use_value is not _UNSET:
            return definition.use_value
        if definition.use_factory is not None:
            deps = [self.resolve(tok, _resolving=resolving) for tok in definition.inject]
            return definition.use_factory(*deps)
        assert definition.use_class is not None
        kwargs = self._resolve_constructor_args(definition.use_class, resolving)
        return definition.use_class(**kwargs)

    def _resolve_constructor_args(self, cls: type, resolving: frozenset) -> dict:
        init = cls.__init__  # type: ignore[misc]  # deliberately dynamic: `cls` is any registered provider class
        if init is object.__init__:
            return {}
        try:
            hints = typing.get_type_hints(init)
        except Exception:
            hints = {}
        signature = inspect.signature(init)
        kwargs: dict[str, Any] = {}
        for name, param in signature.parameters.items():
            if name == "self" or param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            default = param.default
            if isinstance(default, InjectMarker):
                kwargs[name] = self.resolve(default.token, _resolving=resolving)
                continue
            if isinstance(default, OptionalMarker):
                hint = hints.get(name)
                try:
                    kwargs[name] = self.resolve(hint, _resolving=resolving) if hint else None
                except ProviderNotFoundError:
                    kwargs[name] = None
                continue

            hint = hints.get(name)
            if hint is not None:
                kwargs[name] = self.resolve(hint, _resolving=resolving)
            elif default is inspect.Parameter.empty:
                raise ProviderNotFoundError(name)
            # else: no annotation, has its own default -> let the class use it.
        return kwargs
