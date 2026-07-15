"""
Metadata storage, modeled after Nest's `@SetMetadata()` / `Reflect.defineMetadata`.

Every decorator in Austial (``@Module``, ``@Controller``, ``@Get``, ``@UseGuards``,
...) ultimately calls :func:`set_metadata` to stash data directly on the
decorated class or function. :class:`Reflector` (see ``reflector.py``) is the
public, Nest-shaped API for reading it back out.
"""

from __future__ import annotations

from typing import Any

_METADATA_ATTR = "__austial_metadata__"

# Well-known metadata keys used across the framework.
MODULE_METADATA = "austial:module"
CONTROLLER_METADATA = "austial:controller"
INJECTABLE_METADATA = "austial:injectable"
ROUTE_METADATA = "austial:route"
GUARDS_METADATA = "austial:guards"
INTERCEPTORS_METADATA = "austial:interceptors"
PIPES_METADATA = "austial:pipes"
FILTERS_METADATA = "austial:filters"
HTTP_CODE_METADATA = "austial:http_code"
HEADER_METADATA = "austial:header"
INJECT_TOKENS_METADATA = "austial:inject_tokens"
CATCH_METADATA = "austial:catch"


def _bucket(target: Any) -> dict:
    bucket = target.__dict__.get(_METADATA_ATTR)
    if bucket is None:
        bucket = {}
        setattr(target, _METADATA_ATTR, bucket)
    return bucket


def set_metadata(key: str, value: Any):
    """Decorator factory: attaches ``value`` under ``key`` on the decorated target.

    Mirrors Nest's ``@SetMetadata(key, value)``. Can decorate classes or
    functions/methods, and is also usable directly as ``set_metadata(k, v)(target)``.
    """

    def decorator(target):
        _bucket(target)[key] = value
        return target

    return decorator


def get_metadata(key: str, target: Any, default: Any = None) -> Any:
    """Reads a single metadata value previously stashed with :func:`set_metadata`."""
    if target is None:
        return default
    bucket = getattr(target, _METADATA_ATTR, None)
    if bucket is None:
        return default
    return bucket.get(key, default)


def has_metadata(key: str, target: Any) -> bool:
    bucket = getattr(target, _METADATA_ATTR, None)
    return bucket is not None and key in bucket
