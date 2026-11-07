"""The DI container -- mirrors Nest's ``IoC`` container.

Providers are resolved from constructor type hints, recursively, with a
singleton cache by default (``Scope.TRANSIENT`` opts a provider out of caching,
``Scope.REQUEST`` caches per request instead). Supports Nest's four "custom provider"
shapes as plain dicts: ``{"provide": TOKEN, "useValue": ...}``,
``{"provide": TOKEN, "useClass": ...}``,
``{"provide": TOKEN, "useFactory": fn, "inject": [...]}`` and
``{"provide": TOKEN, "useExisting": OTHER_TOKEN}`` (an alias).
"""

from __future__ import annotations

import inspect
import types
import typing
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from austial.common.decorators.injectable import InjectMarker, OptionalMarker
from austial.common.enums import Scope
from austial.core.forward_ref import ForwardReference, LazyProvider, unwrap
from austial.core.metadata import INJECTABLE_METADATA, MODULE_METADATA, get_metadata
from austial.core.module_ref import ModuleRef
from austial.core.request_context import REQUEST, get_current_context
from austial.core.tokens import GLOBAL_COMPONENT_KINDS

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
        super().__init__(
            f"Circular dependency detected while resolving '{name}'. "
            f"Break the cycle with `Inject(forward_ref(lambda: Other))` on one side."
        )


class RequestScopeError(Exception):
    def __init__(self, token: Any):
        name = getattr(token, "__name__", token)
        super().__init__(
            f"'{name}' is request-scoped (or depends on the REQUEST token / a request-scoped provider) "
            f"and can only be resolved while handling a request. Outside one, use "
            f"`ModuleRef.resolve(Token, ContextIdFactory.create())`."
        )


class AsyncProviderNotInitializedError(Exception):
    def __init__(self, token: Any):
        name = getattr(token, "__name__", token)
        super().__init__(
            f"'{name}' is built by an async factory that hasn't run yet. Async providers are awaited when the "
            f"application initialises: use `await app.init()` (automatic under `austial serve`/uvicorn, "
            f"`create_application_context()` and `await Test...compile()`)."
        )


@dataclass
class ProviderDefinition:
    token: Any
    use_class: type | None = None
    use_value: Any = _UNSET
    use_factory: Callable | None = None
    use_existing: Any = _UNSET
    inject: Sequence[Any] = field(default_factory=list)
    scope: Scope = Scope.DEFAULT
    is_async: bool = False  # `use_factory` is a coroutine function, awaited by init_async_providers()


@dataclass
class ModuleRecord:
    """What a module contributed to the container, in registration order -- the lifecycle
    manager walks these to run hooks module by module, dependencies first."""

    module: type | None
    providers: list = field(default_factory=list)
    controllers: list = field(default_factory=list)


@dataclass
class _Dependency:
    name: str
    token: Any
    optional: bool = False
    lazy: bool = False
    defaulted: bool = False  # the parameter has its own default value


def _unwrap_optional(hint: Any) -> Any:
    """``X`` for ``X | None`` / ``Optional[X]`` (exactly one non-None member), else ``None``."""
    if typing.get_origin(hint) not in (typing.Union, types.UnionType):
        return None
    members = typing.get_args(hint)
    non_none = [arg for arg in members if arg is not type(None)]
    return non_none[0] if len(non_none) == 1 and len(members) == 2 else None


class Container:
    """One container per application. Every module's providers/controllers
    register into the same container (Nest's DI graph is application-wide
    too, scoped by module `exports`/`imports` only at the *visibility* level,
    which Austial does not currently enforce for simplicity)."""

    def __init__(self):
        from austial.core.discovery import DiscoveryService
        from austial.core.lazy_module_loader import LazyModuleLoader
        from austial.core.lifecycle import LifecycleManager

        self._definitions: dict[Any, ProviderDefinition] = {}
        self._singletons: dict[Any, Any] = {}
        self._controllers: list[type] = []
        self._scope_cache: dict[Any, bool] = {}
        self._global_components: dict[str, list[Any]] = {kind: [] for kind in GLOBAL_COMPONENT_KINDS.values()}
        self.module_records: list[ModuleRecord] = []
        # Called for a token nothing registered (see TestingModuleBuilder.use_mocker); returns a stand-in or None.
        self.mocker: Callable[[Any], Any] | None = None
        self.internal_tokens: set[Any] = set()  # framework-provided tokens, hidden from DiscoveryService
        self.lifecycle = LifecycleManager(self)
        module_ref = ModuleRef(self)
        for token, instance in (
            (ModuleRef, module_ref),
            (DiscoveryService, DiscoveryService(self)),
            (LazyModuleLoader, LazyModuleLoader(self, module_ref)),
        ):
            self.set_instance(token, instance)
            self.internal_tokens.add(token)

    # -- registration -----------------------------------------------------------------
    def register(self, provider: Any) -> ProviderDefinition:
        if isinstance(provider, dict) and isinstance(provider.get("provide"), str):
            kind = GLOBAL_COMPONENT_KINDS.get(provider["provide"])
            if kind is not None:
                # APP_GUARD & co. may be registered many times: file each one under its own unique token.
                unique = f"{provider['provide']}#{len(self._global_components[kind])}"
                self._global_components[kind].append(unique)
                provider = {**provider, "provide": unique}
        definition = self._normalize(provider)
        self._definitions[definition.token] = definition
        self._scope_cache.clear()
        return definition

    def register_controller(self, controller: type) -> None:
        self.register(controller)
        if controller not in self._controllers:
            self._controllers.append(controller)

    def has(self, token: Any) -> bool:
        return token in self._definitions or token in self._singletons

    def set_instance(self, token: Any, instance: Any) -> None:
        """Registers an already-built instance under `token` (used for
        controllers, which the router builder constructs itself)."""
        self._singletons[token] = instance
        self._definitions.setdefault(token, ProviderDefinition(token=token, use_value=instance))
        self._scope_cache.clear()

    def global_components(self, kind: str) -> list[Any]:
        """Tokens of the providers registered under ``APP_GUARD``/``APP_PIPE``/``APP_INTERCEPTOR``/
        ``APP_FILTER`` (``kind`` is ``"guards"``, ``"pipes"``, ``"interceptors"`` or ``"filters"``),
        in registration order."""
        return list(self._global_components[kind])

    @property
    def controllers(self) -> list[type]:
        return list(self._controllers)

    def definitions(self) -> list[ProviderDefinition]:
        """Every registered provider definition, in registration order (modules and
        controllers included -- filter with :meth:`is_module` / :attr:`controllers`)."""
        return list(self._definitions.values())

    def is_module(self, token: Any) -> bool:
        return isinstance(token, type) and get_metadata(MODULE_METADATA, token) is not None

    def _normalize(self, provider: Any) -> ProviderDefinition:
        if isinstance(provider, dict):
            token = unwrap(provider["provide"])
            if "useValue" in provider:
                return ProviderDefinition(token=token, use_value=provider["useValue"])
            if "useClass" in provider:
                use_class = unwrap(provider["useClass"])
                scope = get_metadata(INJECTABLE_METADATA, use_class, {}).get("scope", Scope.DEFAULT)
                return ProviderDefinition(token=token, use_class=use_class, scope=scope)
            if "useFactory" in provider:
                factory = provider["useFactory"]
                is_async = inspect.iscoroutinefunction(factory)
                scope = provider.get("scope", Scope.DEFAULT)
                if is_async and scope != Scope.DEFAULT:
                    raise ValueError("An async factory provider must be a singleton (scope DEFAULT).")
                return ProviderDefinition(
                    token=token,
                    use_factory=factory,
                    inject=provider.get("inject", []),
                    scope=scope,
                    is_async=is_async,
                )
            if "useExisting" in provider:
                return ProviderDefinition(token=token, use_existing=unwrap(provider["useExisting"]))
            raise ValueError(f"Invalid provider definition: {provider!r}")
        # Plain class shorthand, e.g. `providers=[HealthService]`.
        provider = unwrap(provider)
        scope = get_metadata(INJECTABLE_METADATA, provider, {}).get("scope", Scope.DEFAULT)
        return ProviderDefinition(token=provider, use_class=provider, scope=scope)

    def _definition_for(self, token: Any) -> ProviderDefinition | None:
        definition = self._definitions.get(token)
        if definition is None and self.mocker is not None:
            mock = self.mocker(token)
            if mock is not None:
                definition = self.register({"provide": token, "useValue": mock})
        if definition is None and isinstance(token, type) and token.__module__ != "builtins":
            # Builtins (`str`, `int`, ...) are never auto-built: `str()` is "", not a dependency.
            # Auto-register unregistered `@Injectable` classes encountered
            # only as a nested constructor dependency -- keeps things
            # working even if a provider was forgotten in `providers=[]`.
            definition = self.register(token)
        return definition

    # -- scopes -----------------------------------------------------------------------
    def is_request_bound(self, token: Any, *, _visiting: frozenset = frozenset()) -> bool:
        """True if resolving ``token`` yields something that only exists within a request:
        a ``Scope.REQUEST`` provider, the ``REQUEST`` token, or anything depending (even
        transitively) on either. Such providers -- and controllers/guards/interceptors built
        on them -- are resolved per request, not once at startup."""
        if isinstance(token, str) and token == REQUEST:
            return True
        if token in self._singletons or token in _visiting:
            return False
        cached = self._scope_cache.get(token)
        if cached is not None:
            return cached
        definition = self._definition_for(token) if (isinstance(token, type) or token in self._definitions) else None
        if definition is None:
            return False
        visiting = _visiting | {token}
        result = definition.scope == Scope.REQUEST or any(
            self.is_request_bound(dep, _visiting=visiting) for dep in self._dependency_tokens(definition)
        )
        if not _visiting:  # only memoise a complete traversal, never one cut short by a cycle
            self._scope_cache[token] = result
        return result

    def _dependency_tokens(self, definition: ProviderDefinition) -> list[Any]:
        if definition.use_existing is not _UNSET:
            return [definition.use_existing]
        if definition.use_factory is not None:
            return [self._factory_token(entry)[0] for entry in definition.inject]
        if definition.use_class is not None:
            try:
                return [
                    dep.token
                    for dep in self._constructor_plan(definition.use_class)
                    if not dep.lazy and self._is_injected(dep)
                ]
            except ProviderNotFoundError:
                return []
        return []

    # -- resolution -------------------------------------------------------------------
    def resolve(self, token: Any, *, _resolving: frozenset = frozenset()) -> Any:
        if isinstance(token, str) and token == REQUEST:
            context = get_current_context()
            if context is None or context.request is None:
                raise RequestScopeError(token)
            return context.request

        if token in self._singletons:
            return self._singletons[token]

        definition = self._definition_for(token)
        if definition is None:
            raise ProviderNotFoundError(token)

        if token in _resolving:
            raise CircularDependencyError(token)
        next_resolving = _resolving | {token}

        if definition.scope == Scope.TRANSIENT:
            return self._instantiate(definition, next_resolving)

        if self.is_request_bound(token):
            context = get_current_context()
            if context is None:
                raise RequestScopeError(token)
            if token not in context.cache:
                context.cache[token] = self._instantiate(definition, next_resolving)
            return context.cache[token]

        instance = self._instantiate(definition, next_resolving)
        self._singletons[token] = instance
        return instance

    def create_instance(self, cls: type) -> Any:
        """Builds ``cls`` with constructor injection, bypassing registration and caching."""
        return cls(**self._resolve_constructor_args(cls, frozenset()))

    @staticmethod
    def _factory_token(entry: Any) -> tuple[Any, bool]:
        """A factory's ``inject`` entry is a token, or ``{"token": T, "optional": True}``."""
        if isinstance(entry, dict):
            return unwrap(entry["token"]), bool(entry.get("optional", False))
        return unwrap(entry), False

    def _instantiate(self, definition: ProviderDefinition, resolving: frozenset) -> Any:
        if definition.use_value is not _UNSET:
            return definition.use_value
        if definition.use_existing is not _UNSET:
            return self.resolve(definition.use_existing, _resolving=resolving)
        if definition.use_factory is not None:
            if definition.is_async:
                raise AsyncProviderNotInitializedError(definition.token)
            return definition.use_factory(*self._factory_args(definition, resolving))
        assert definition.use_class is not None
        kwargs = self._resolve_constructor_args(definition.use_class, resolving)
        return definition.use_class(**kwargs)

    def _factory_args(self, definition: ProviderDefinition, resolving: frozenset) -> list[Any]:
        args: list[Any] = []
        for entry in definition.inject:
            token, optional = self._factory_token(entry)
            try:
                args.append(self.resolve(token, _resolving=resolving))
            except ProviderNotFoundError:
                if not optional:
                    raise
                args.append(None)
        return args

    async def init_async_providers(self) -> None:
        """Awaits every ``useFactory`` provider whose factory is ``async``, dependencies first, and
        caches the results as singletons -- after which they resolve like any other provider. Called
        when the application initialises; idempotent."""
        done: set[Any] = set()
        for definition in list(self._definitions.values()):
            await self._ensure_ready(definition.token, done)

    async def _ensure_ready(self, token: Any, done: set[Any]) -> None:
        if token in done or token in self._singletons:
            return
        done.add(token)
        definition = self._definitions.get(token)
        if definition is None and isinstance(token, type):
            definition = self._definition_for(token)
        if definition is None or definition.scope != Scope.DEFAULT or self.is_request_bound(token):
            return
        for dep in self._dependency_tokens(definition):
            await self._ensure_ready(dep, done)
        if definition.is_async and definition.use_factory is not None:
            args = self._factory_args(definition, frozenset({token}))
            self._singletons[token] = await definition.use_factory(*args)

    def _constructor_plan(self, cls: type) -> list[_Dependency]:
        init = cls.__init__  # type: ignore[misc]  # deliberately dynamic: `cls` is any registered provider class
        if init is object.__init__:
            return []
        try:
            hints = typing.get_type_hints(init)
        except Exception:
            hints = {}
        signature = inspect.signature(init)
        plan: list[_Dependency] = []
        for name, param in signature.parameters.items():
            if name == "self" or param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            default = param.default
            if isinstance(default, InjectMarker):
                if isinstance(default.token, ForwardReference):
                    plan.append(_Dependency(name, default.token, lazy=True))
                else:
                    plan.append(_Dependency(name, default.token))
                continue
            if isinstance(default, OptionalMarker):
                hint = hints.get(name)
                plan.append(_Dependency(name, hint, optional=True))
                continue

            hint = hints.get(name)
            if hint is not None:
                has_default = default is not inspect.Parameter.empty
                inner = _unwrap_optional(hint)
                if inner is not None:
                    # `Dep | None`: inject `Dep` when the container provides it, else None / the default.
                    plan.append(_Dependency(name, inner, optional=not has_default, defaulted=has_default))
                else:
                    plan.append(_Dependency(name, hint, defaulted=has_default))
            elif default is inspect.Parameter.empty:
                raise ProviderNotFoundError(name)
            # else: no annotation, has its own default -> let the class use it.
        return plan

    def _is_injected(self, dep: _Dependency) -> bool:
        """A parameter with a default value is only injected when its type is something the
        container actually provides (registered, or an ``@Injectable`` class). Otherwise
        ``def __init__(self, retries: int = 3)`` would be handed a built ``int()`` instead of ``3``."""
        if not dep.defaulted or dep.lazy:
            return True
        return self.has(dep.token) or (
            isinstance(dep.token, type) and get_metadata(INJECTABLE_METADATA, dep.token) is not None
        )

    def _resolve_constructor_args(self, cls: type, resolving: frozenset) -> dict:
        kwargs: dict[str, Any] = {}
        for dep in self._constructor_plan(cls):
            if not self._is_injected(dep):
                continue  # let the class use its own default
            if dep.lazy:
                kwargs[dep.name] = LazyProvider(self, unwrap(dep.token))
            elif dep.optional:
                try:
                    kwargs[dep.name] = self.resolve(dep.token, _resolving=resolving) if dep.token else None
                except ProviderNotFoundError:
                    kwargs[dep.name] = None
            else:
                kwargs[dep.name] = self.resolve(dep.token, _resolving=resolving)
        return kwargs
