"""``AuthGuard`` -- bearer-token verification for every request.

Runs before the handler (see the request pipeline in ``austial.core``). Skips routes
marked ``@Public``. On success, populates ``request.state.user`` with an
``AuthPrincipal`` so ``CurrentUser`` can retrieve it. On failure, raises
``UnauthorizedException`` (401).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from austial.auth.decorators import is_public
from austial.auth.errors import AuthenticationError, InvalidTokenError
from austial.auth.jwt_strategy import JwtStrategy, TokenPayload
from austial.common.decorators.injectable import Injectable
from austial.common.guards.base import CanActivate, ExecutionContext


@dataclass(frozen=True, slots=True)
class AuthPrincipal:
    """The authenticated caller. ``subject`` is the user id; ``claims`` is the JWT
    payload minus system claims. Accessible via ``CurrentUser()`` or
    ``request.state.user``."""

    subject: str
    claims: dict[str, Any]
    token_id: str | None = None


@Injectable()
class AuthGuard(CanActivate):
    """Verifies a ``Bearer`` token from the ``Authorization`` header via ``JwtStrategy``.

    Product code can subclass this to enforce additional claims (tenant, roles, session
    freshness) after the base verification succeeds -- override ``after_verify`` and
    raise ``UnauthorizedException`` to reject."""

    def __init__(self, jwt_strategy: JwtStrategy) -> None:
        self._jwt = jwt_strategy

    async def can_activate(self, context: ExecutionContext) -> bool:
        handler = context.get_handler()
        controller = context.get_class()
        if is_public(handler) or is_public(controller):
            return True

        request = context.get_request()
        header = request.headers.get("Authorization", "")
        if not header or not header.lower().startswith("bearer "):
            raise AuthenticationError("missing bearer token")

        token = header.split(" ", 1)[1].strip()
        if not token:
            raise InvalidTokenError("empty bearer token")

        payload = self._jwt.verify(token)
        principal = AuthPrincipal(subject=payload.subject, claims=payload.claims, token_id=payload.token_id)
        await self.after_verify(request, payload, principal)
        request.state.user = principal
        return True

    async def after_verify(self, request: Any, payload: TokenPayload, principal: AuthPrincipal) -> None:
        """Hook for subclasses to add checks (e.g. session revocation) after the
        base signature/expiry checks pass. Raise an exception to reject."""
        # base implementation intentionally does nothing
