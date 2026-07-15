"""Kept intentionally lightweight (no imports of ``app``/``factory``/``router_builder``)
so that low-level modules like ``austial.core.metadata`` can be imported from
deep within ``austial.common.decorators`` without triggering a circular import.
``AustialApplication``/``AustialFactory`` are imported directly from
``austial.core.app`` / ``austial.core.factory`` by ``austial/__init__.py``,
*after* ``austial.common`` has fully loaded.
"""

from austial.core.container import CircularDependencyError, Container, ProviderNotFoundError
from austial.core.dynamic_module import DynamicModule
from austial.core.reflector import Reflector

__all__ = [
    "Container",
    "ProviderNotFoundError",
    "CircularDependencyError",
    "DynamicModule",
    "Reflector",
]
