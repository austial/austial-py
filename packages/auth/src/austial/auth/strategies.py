"""Pluggable authentication strategies -- the ``@nestjs/passport`` workflow without Passport.

A strategy is an injectable class with a ``name`` and a ``validate(request)`` that returns the authenticated user, or
raises ``AuthenticationError`` (``401``). A guard built from one or more names tries them in order and accepts the first
that succeeds::

    @Injectable()
    class ApiKeyStrategy(AuthStrategy):
        name = "api-key"

        def __init__(self, keys: KeysService):
            self.keys = keys

        async def validate(self, request):
            owner = await self.keys.owner_of(request.headers.get("x-api-key", ""))
            if owner is None:
                raise AuthenticationError("invalid API key")
            return owner

    @Module(providers=[ApiKeyStrategy, KeysService])
    class AuthModule: ...

    @Controller("reports")
    @UseGuards(StrategyGuard("jwt", "api-key"))        # a bearer token or an API key
    class ReportsController:
        @Get()
        def list(self, user=CurrentUser()): ...

The accepted user lands in ``request.state.user``, where ``CurrentUser()`` reads it. ``@Public`` routes skip the guard.
Strategies are discovered from the providers of every module, so any module can contribute one. ``JwtBearerStrategy``
(name ``"jwt"``) wraps :class:`JwtStrategy` and is available when ``AuthModule`` is imported.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from austial.auth.auth_guard import AuthPrincipal
from austial.auth.decorators import is_public
from austial.auth.errors import AuthenticationError, InvalidTokenError
from austial.auth.jwt_strategy import JwtStrategy
from austial.common.decorators.injectable import Injectable
from austial.common.guards.base import CanActivate, ExecutionContext
from austial.core.discovery import DiscoveryService
from austial.core.module_ref import ModuleRef


class AuthStrategy(ABC):
    """Base class of strategies; set ``name`` and implement ``validate``."""

    name: str

    @abstractmethod
    async def validate(self, request: Any) -> Any:
        """Returns the authenticated user, or raises ``AuthenticationError``."""


@Injectable()
class JwtBearerStrategy(AuthStrategy):
    name = "jwt"

    def __init__(self, jwt: JwtStrategy):
        self._jwt = jwt

    async def validate(self, request: Any) -> AuthPrincipal:
        header = request.headers.get("Authorization", "")
        if not header.lower().startswith("bearer "):
            raise AuthenticationError("missing bearer token")
        token = header.split(" ", 1)[1].strip()
        if not token:
            raise InvalidTokenError("empty bearer token")
        payload = self._jwt.verify(token)
        return AuthPrincipal(subject=payload.subject, claims=payload.claims, token_id=payload.token_id)


@Injectable()
class StrategyRegistry:
    """Finds the strategies registered anywhere in the application, by name."""

    def __init__(self, discovery: DiscoveryService, module_ref: ModuleRef):
        self._discovery, self._module_ref = discovery, module_ref

    def get(self, name: str) -> AuthStrategy:
        for wrapper in self._discovery.get_providers():  # providers are built lazily: match on the class, then resolve
            cls = wrapper.metatype
            if isinstance(cls, type) and issubclass(cls, AuthStrategy) and getattr(cls, "name", None) == name:
                strategy: AuthStrategy = self._module_ref.get(wrapper.token)
                return strategy
        raise LookupError(f"No authentication strategy named '{name}' is registered")


def StrategyGuard(*names: str) -> type[CanActivate]:  # noqa: N802
    """A guard class accepting a request when any named strategy validates it (tried in order). When none does, the
    *first* strategy's error is raised."""
    if not names:
        raise ValueError("StrategyGuard needs at least one strategy name")

    @Injectable()
    class _StrategyGuard(CanActivate):
        def __init__(self, registry: StrategyRegistry):
            self._registry = registry

        async def can_activate(self, context: ExecutionContext) -> bool:
            if is_public(context.get_handler()) or is_public(context.get_class()):
                return True
            request = context.get_request()
            first_error: AuthenticationError | None = None
            for name in names:
                try:
                    user = await self._registry.get(name).validate(request)
                except AuthenticationError as exc:
                    first_error = first_error or exc
                    continue
                request.state.user = user
                return True
            raise first_error or AuthenticationError("authentication failed")

    _StrategyGuard.__name__ = f"StrategyGuard({', '.join(names)})"
    return _StrategyGuard
