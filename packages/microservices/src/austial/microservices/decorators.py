"""``@MessagePattern``, ``@EventPattern``, ``@Payload`` and ``@Ctx`` -- mirror ``@nestjs/microservices``.

::

    @Controller()
    class MathController:
        @MessagePattern({"cmd": "sum"})                  # request-response: the return value is the reply
        def accumulate(self, numbers: list[int] = Payload()) -> int:
            return sum(numbers)

        @EventPattern("user.created")                    # fire-and-forget: nothing is returned to the sender
        async def on_user_created(self, user: dict = Payload()): ...
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from austial.core.metadata import get_metadata, set_metadata

MESSAGE_PATTERN_METADATA = "austial:rpc:message_pattern"
EVENT_PATTERN_METADATA = "austial:rpc:event_pattern"


def MessagePattern(pattern: Any) -> Callable:  # noqa: N802
    return set_metadata(MESSAGE_PATTERN_METADATA, pattern)


def EventPattern(pattern: Any) -> Callable:  # noqa: N802
    def decorator(fn):
        existing = list(get_metadata(EVENT_PATTERN_METADATA, fn, []))
        set_metadata(EVENT_PATTERN_METADATA, [*existing, pattern])(fn)
        return fn

    return decorator


class PayloadMarker:
    def __init__(self, key: str | None):
        self.key = key


class CtxMarker:
    pass


def Payload(key: str | None = None) -> Any:  # noqa: N802
    """The message data (or, with ``key``, one field of it)."""
    return PayloadMarker(key)


def Ctx() -> Any:  # noqa: N802
    """An :class:`RpcContext` with the pattern that matched."""
    return CtxMarker()
