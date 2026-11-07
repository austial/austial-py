"""Decorators: ``@RateLimit(limit, period_seconds)``.

Attaches per-route metadata that ``RateLimitGuard`` reads to override
``SecurityConfig.default_rate_limit`` for that handler.
"""

from __future__ import annotations

from collections.abc import Callable

from austial.core.metadata import get_metadata, set_metadata

RATE_LIMIT_METADATA = "austial:security:rate_limit"


def RateLimit(limit: int, period_seconds: int) -> Callable:  # noqa: N802 - decorator naming
    """Override the rate-limit budget for a single handler or controller.

    ``limit`` is the maximum number of requests inside a fixed window of
    ``period_seconds`` seconds. Raises ``ValueError`` at decoration time on a
    non-positive value so misconfiguration surfaces at import."""

    if limit <= 0:
        raise ValueError("RateLimit limit must be positive")
    if period_seconds <= 0:
        raise ValueError("RateLimit period_seconds must be positive")

    def decorator(target):
        set_metadata(RATE_LIMIT_METADATA, (limit, period_seconds))(target)
        return target

    return decorator


def get_rate_limit(target, default: tuple[int, int]) -> tuple[int, int]:
    """Return the rate-limit tuple attached to ``target`` (or ``default``)."""
    value = get_metadata(RATE_LIMIT_METADATA, target, None)
    if value is None:
        return default
    return value
